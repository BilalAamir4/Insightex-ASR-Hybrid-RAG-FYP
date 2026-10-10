"""Enqueue an `ingest_file` job: stage a copy of a local file, hash it, de-duplicate, queue it (ADR-0036).

`enqueue_file` (CLI) copies a path into staging and calls `enqueue_staged`; the HTTP upload receives the body
straight into staging and calls `enqueue_staged` too. Validation of the media itself
(probe, codecs, duration, ...) happens in the job, so a rejection reaches the user through the job record.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from insightex.asr.languages import require_language
from insightex.core.config import Settings
from insightex.asr.stage import AsrStage
from insightex.asr.transcript import SCHEMA_VERSION, TRANSCRIPT_JSON
from insightex.ingest import staging
from insightex.ingest.errors import ErrorCode, IngestRejected
from insightex.ingest.settings import IngestSettings
from insightex.jobs import store
from insightex.jobs.workspace import Workspaces
from insightex.media import engine
from insightex.sources.identity import workspace_id_for_bytes

KIND = "ingest_file"
_lock = threading.Lock()  # check-then-enqueue must not interleave between threads of one process


@dataclass(frozen=True)
class FileIngest:
    workspace_id: str
    job_id: str | None  # None when an up-to-date lecture already exists and no job was needed
    deduplicated: bool
    rejected: IngestRejected | None = None  # set when the file was refused before staging; job_id is then a failed job


def _current_lecture(workspaces: Workspaces, workspace_id: str, language_id: str) -> bool:
    """True if the workspace holds a finished `normalise` made by the current normaliser version and a finished
    `asr` transcript in `language_id` made by the current stage version (another language means a new ASR run)."""
    directory = workspaces.stage_output_dir(workspace_id, "normalise")
    if directory is None or not (directory / engine.VIDEO_NAME).is_file():
        return False
    try:
        info = json.loads((directory / "normalise.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if info.get("normaliser_version") != engine.NORMALISER_VERSION:
        return False
    asr_dir = workspaces.stage_output_dir(workspace_id, AsrStage.name)
    if asr_dir is None:
        return False
    try:
        doc = json.loads((asr_dir / TRANSCRIPT_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (doc.get("language", {}).get("id") == language_id and doc.get("stage_version") == AsrStage.version
            and doc.get("schema_version") == SCHEMA_VERSION)


def enqueue_file(
    conn: sqlite3.Connection,
    settings: Settings,
    path: Path,
    *,
    language: str | None,
    via: str = "cli",
    original_filename: str | None = None,
) -> FileIngest:
    """Stage `path` and queue its ingest. Raises IngestRejected(INSUFFICIENT_DISK) before anything is copied.

    Order: free-space check, copy while hashing, then (under a lock) look for an active job for the same
    bytes, then an up-to-date finished lecture, else enqueue. A duplicate's staged copy is deleted. An older
    normaliser version re-normalises into the same workspace. An empty or oversized file is refused from its
    size alone, before the free-space check and the copy: the result carries `rejected` and a job already in
    state `failed`. The media itself is judged by the job.
    """
    require_language(settings, language)  # before anything else: a bad language leaves no trace
    cfg = IngestSettings.from_settings(settings)
    size = path.stat().st_size
    try:  # rule 1 on the file as it is: refuse before copying anything, but keep a failed job in the history
        engine.check_size(size, cfg.max_download_bytes)
    except IngestRejected as rejected:
        return _record_rejection(conn, path, rejected, via, original_filename, language)
    directory = staging.staging_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    engine.check_disk(size, directory, cfg)

    staged = staging.copy_to_staging(path, settings)
    return enqueue_staged(conn, settings, staged, language=language, via=via,
                          original_filename=original_filename or path.name)


def enqueue_staged(
    conn: sqlite3.Connection,
    settings: Settings,
    staged: staging.StagedFile,
    *,
    language: str | None,
    via: str,
    original_filename: str | None,
) -> FileIngest:
    """Queue the ingest of a copy that is already in staging (the CLI copied it, or the HTTP upload received it).

    Under a lock: an active job for the same bytes and language is returned, then an up-to-date finished lecture
    transcribed in that language; in both cases the staged copy is deleted. Otherwise the job is enqueued and
    owns the staged copy. A missing or unknown language raises IngestError and deletes the staged copy.
    """
    try:
        lang = require_language(settings, language)
    except Exception:
        staging.remove_staged(settings, staged.name)
        raise
    workspace_id = workspace_id_for_bytes(staged.sha256)
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    with _lock:
        for status in ("running", "queued"):
            for job in store.list_jobs(conn, limit=1000, status=status):
                if job.kind == KIND and job.workspace_id == workspace_id and job.payload.get("language") == lang.id:
                    staging.remove_staged(settings, staged.name)
                    return FileIngest(workspace_id, job.id, True)
        if _current_lecture(workspaces, workspace_id, lang.id):
            staging.remove_staged(settings, staged.name)
            return FileIngest(workspace_id, None, True)
        payload = {
            "staged": staged.name,
            "sha256": staged.sha256,
            "size_bytes": staged.size_bytes,
            "original_filename": staging.sanitise_filename(original_filename),
            "received_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "via": via,
            "language": lang.id,
        }
        job_id = store.enqueue(conn, KIND, payload, workspace_id)
    return FileIngest(workspace_id, job_id, False)


def _record_rejection(conn, path: Path, rejected: IngestRejected, via: str, original_filename: str | None,
                      language: str | None) -> FileIngest:
    payload = {"staged": None, "original_filename": staging.sanitise_filename(original_filename or path.name), "via": via,
               "language": language}
    job_id = uuid.uuid4().hex
    text = f"{ErrorCode(rejected.code)}: {rejected.message}"
    workspace_id = f"rejected-{job_id}"  # a placeholder: the file was never hashed and no workspace exists
    store.enqueue(
        conn, KIND, payload, workspace_id, job_id=job_id,
        failed=(f"fetch failed: IngestRejected: {text}", f"IngestRejected: {text}\ndetails:\n{rejected.details}"),
    )
    return FileIngest(workspace_id, job_id, False, rejected)


_REJECTED_RE = re.compile(r"IngestRejected: ([A-Z_]+): (.*)")
_FAILED_CODE_RE = re.compile(r"(?:IngestError|AsrError): ([A-Z_]+): (.*)")


def job_outcome(conn: sqlite3.Connection, settings: Settings, job_id: str, *, poll_s: float = 1.0) -> dict:
    """Block until the job ends; describe it: status ("succeeded", "rejected", "failed", "cancelled"), code, message, warnings."""
    while True:
        job = store.get_job(conn, job_id)
        if job.status in store.FINAL_STATUSES:
            break
        time.sleep(poll_s)
    out: dict = {"status": job.status, "code": None, "message": None, "warnings": []}
    if job.status == "failed":
        m = _REJECTED_RE.search(job.error or "")
        f = None if m else _FAILED_CODE_RE.search(job.error or "")
        if m:
            out.update(status="rejected", code=m.group(1), message=m.group(2))
        elif f:
            out.update(code=f.group(1), message=f.group(2))
        else:
            out["message"] = job.error
    elif job.status == "succeeded":
        workspaces = Workspaces(settings.jobs.workspaces_dir)
        for stage, name in (("normalise", "normalise.json"), (AsrStage.name, TRANSCRIPT_JSON)):
            directory = workspaces.stage_output_dir(job.workspace_id, stage)
            try:
                out["warnings"] += json.loads((directory / name).read_text(encoding="utf-8")).get("warnings", [])
            except (OSError, ValueError, TypeError):
                pass
    return out
