"""The extraction hold (ADR-0054 decision 8, Amendment 1).

A lecture ingested with `--hold-extract` (CLI only) runs every stage except `extract`. The worker records the hold
in the workspace manifest as `extract_hold: {set_at, job_id}`; while it has no `released_at`, every later job on
the workspace skips `extract` too (sticky), eviction leaves the workspace alone, and a re-add is a no-op once the
other stages are cached. `insightex extract-hold release <id>` enqueues an `extract_hold_release` job, and the worker
writes `released_at`. Only the worker writes manifests; the CLI only reads them for its checks.

The checks before a hold job is created (`check_hold_allowed`): no queued or running job on the workspace
(`EXTRACT_HOLD_JOB_ACTIVE`), and no published `extract` output under any key (`EXTRACT_HOLD_AFTER_EXTRACTION`).
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from typing import Any

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.jobs import store
from insightex.jobs.workspace import Workspaces

log = logging.getLogger(__name__)

MANIFEST_KEY = "extract_hold"
STAGE_NAME = "extract"
RELEASE_KIND = "extract_hold_release"
NO_HOLD_MESSAGE = "This lecture has no active extraction hold."
NON_YOUTUBE_MESSAGE = ("A hold needs the lecture id before the job starts, and this link only gets one after download. "
                       "Download the file and use: insightex ingest-file <path> --hold-extract")


class HoldRefused(Exception):
    """A hold request refused before any job, with a message and no error code (Amendment 1 items 1 and 5)."""


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def active_hold(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """The manifest's hold record if it is unreleased, else None."""
    h = manifest.get(MANIFEST_KEY)
    return h if isinstance(h, dict) and not h.get("released_at") else None


def record_hold(workspaces: Workspaces, workspace_id: str, job_id: str) -> None:
    """Worker only: record a hold for this job, keeping an earlier unreleased one as it is (the hold is sticky)."""
    manifest = workspaces.read_manifest(workspace_id)
    if active_hold(manifest) is not None:
        return
    manifest[MANIFEST_KEY] = {"set_at": _now(), "job_id": job_id}
    workspaces.write_manifest(workspace_id, manifest)
    log.info("extraction hold recorded for %s (job %s)", workspace_id, job_id)


def release_action(conn: sqlite3.Connection, workspaces: Workspaces, job: store.Job, settings: Any) -> None:
    """The `extract_hold_release` job: write `released_at` into the hold record (kept). No lease, no stages.

    A hold that is already released when the job runs (two releases queued) is left as it is; the job succeeds."""
    manifest = workspaces.read_manifest(job.workspace_id)
    h = active_hold(manifest)
    if h is None:
        log.info("extract_hold_release: %s has no unreleased hold; nothing to do", job.workspace_id)
        return
    h["released_at"] = _now()
    h["released_by_job_id"] = job.id
    workspaces.write_manifest(job.workspace_id, manifest)
    log.info("extraction hold released for %s", job.workspace_id)


def extracted_before(workspaces: Workspaces, workspace_id: str) -> bool:
    """True if the workspace has a published `extract` output under any key (any version, any configuration)."""
    root = workspaces.path(workspace_id) / "stages" / STAGE_NAME
    return root.is_dir() and any(p.is_dir() for p in root.iterdir())


def active_job(conn: sqlite3.Connection, workspace_id: str) -> store.Job | None:
    """A queued or running job of any kind on the workspace, or None."""
    for status in ("running", "queued"):
        for job in store.list_jobs(conn, limit=100000, status=status):
            if job.workspace_id == workspace_id:
                return job
    return None


def check_hold_allowed(conn: sqlite3.Connection, workspaces: Workspaces, workspace_id: str) -> None:
    """Raise IngestError if a hold job must not be created for this workspace (Amendment 1 item 2, decision 8)."""
    if active_job(conn, workspace_id) is not None:
        raise IngestError(ErrorCode.EXTRACT_HOLD_JOB_ACTIVE)
    if extracted_before(workspaces, workspace_id):
        raise IngestError(ErrorCode.EXTRACT_HOLD_AFTER_EXTRACTION)


def held_workspaces(workspaces: Workspaces) -> list[dict[str, Any]]:
    """Every workspace with an unreleased hold: [{workspace_id, set_at, job_id}], sorted by id. Unreadable manifests
    are listed with `error` so a hold is never hidden."""
    out = []
    root = workspaces.root
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        try:
            h = active_hold(workspaces.read_manifest(d.name))
        except (ValueError, OSError) as e:
            out.append({"workspace_id": d.name, "error": f"manifest unreadable: {e}"})
            continue
        if h is not None:
            out.append({"workspace_id": d.name, "set_at": h.get("set_at"), "job_id": h.get("job_id")})
    return out
