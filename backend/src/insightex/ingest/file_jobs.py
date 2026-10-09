"""Enqueue an `ingest_file` job: stage a copy of a local file, hash it, de-duplicate, queue it (ADR-0036).

The same function serves the CLI now and the HTTP upload in M2 session 2. Validation of the media itself
(probe, codecs, duration, ...) happens in the job, so a rejection reaches the user through the job record.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from insightex.core.config import Settings
from insightex.ingest import staging
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


def _current_lecture(workspaces: Workspaces, workspace_id: str) -> bool:
    """True if the workspace holds a finished `normalise` made by the current normaliser version."""
    directory = workspaces.stage_output_dir(workspace_id, "normalise")
    if directory is None or not (directory / engine.VIDEO_NAME).is_file():
        return False
    try:
        info = json.loads((directory / "normalise.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return info.get("normaliser_version") == engine.NORMALISER_VERSION


def enqueue_file(
    conn: sqlite3.Connection,
    settings: Settings,
    path: Path,
    *,
    via: str = "cli",
    original_filename: str | None = None,
) -> FileIngest:
    """Stage `path` and queue its ingest. Raises IngestRejected for an empty or oversized file or too little disk.

    Order: size and free-space checks, copy while hashing, then (under a lock) look for an active job for
    the same bytes, then an up-to-date finished lecture, else enqueue. A duplicate's staged copy is deleted.
    An older normaliser version re-normalises into the same workspace.
    """
    cfg = IngestSettings.from_settings(settings)
    size = path.stat().st_size
    engine.check_size(size, cfg.max_download_bytes)
    directory = staging.staging_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    engine.check_disk(size, directory, cfg)

    staged = staging.copy_to_staging(path, settings)
    workspace_id = workspace_id_for_bytes(staged.sha256)
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    with _lock:
        for status in ("running", "queued"):
            for job in store.list_jobs(conn, limit=1000, status=status):
                if job.kind == KIND and job.workspace_id == workspace_id:
                    staging.remove_staged(settings, staged.name)
                    return FileIngest(workspace_id, job.id, True)
        if _current_lecture(workspaces, workspace_id):
            staging.remove_staged(settings, staged.name)
            return FileIngest(workspace_id, None, True)
        payload = {
            "staged": staged.name,
            "sha256": staged.sha256,
            "size_bytes": staged.size_bytes,
            "original_filename": staging.sanitise_filename(original_filename or path.name),
            "received_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "via": via,
        }
        job_id = store.enqueue(conn, KIND, payload, workspace_id)
    return FileIngest(workspace_id, job_id, False)


_REJECTED_RE = re.compile(r"IngestRejected: ([A-Z_]+): (.*)")


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
        if m:
            out.update(status="rejected", code=m.group(1), message=m.group(2))
        else:
            out["message"] = job.error
    elif job.status == "succeeded":
        directory = Workspaces(settings.jobs.workspaces_dir).stage_output_dir(job.workspace_id, "normalise")
        try:
            out["warnings"] = json.loads((directory / "normalise.json").read_text(encoding="utf-8")).get("warnings", [])
        except (OSError, ValueError, TypeError):
            pass
    return out
