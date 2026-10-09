"""Run ingest_link jobs in-process (no worker subprocess), for tests."""

from __future__ import annotations

import os

from insightex.core.config import Settings, get_settings
from insightex.ingest.link_jobs import enqueue_link
from insightex.jobs import db, store
from insightex.jobs.runner import run_job
from insightex.jobs.workspace import Workspaces


def open_db(settings: Settings | None = None):
    settings = settings or get_settings()
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    return conn


def run_link_job(url: str, settings: Settings | None = None, conn=None) -> store.Job:
    """Enqueue `url`, claim the job and run it to its end; return the job as the database then holds it."""
    settings = settings or get_settings()
    conn = conn or open_db(settings)
    job_id, _workspace_id, _dedup = enqueue_link(conn, settings, url)
    claimed = store.claim_next(conn, os.getpid())
    assert claimed is not None and claimed.id == job_id
    run_job(conn, claimed, settings, Workspaces(settings.jobs.workspaces_dir))
    return store.get_job(conn, job_id)


def run_file_job(path, settings: Settings | None = None, conn=None):
    """Stage `path`, enqueue it, run the job in-process. Returns (FileIngest, Job or None when no job was needed)."""
    from insightex.ingest.file_jobs import enqueue_file

    settings = settings or get_settings()
    conn = conn or open_db(settings)
    result = enqueue_file(conn, settings, path, via="cli")
    if result.job_id is None or result.deduplicated:
        return result, None if result.job_id is None else store.get_job(conn, result.job_id)
    claimed = store.claim_next(conn, os.getpid())
    assert claimed is not None and claimed.id == result.job_id
    run_job(conn, claimed, settings, Workspaces(settings.jobs.workspaces_dir))
    return result, store.get_job(conn, result.job_id)
