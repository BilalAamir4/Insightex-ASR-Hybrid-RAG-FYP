"""GET /api/jobs, /api/jobs/{id}, /api/jobs/{id}/events (SSE); POST /api/jobs/{id}/cancel and /retry."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from insightex.api.deps import connection, settings_of, workspaces_of
from insightex.api.errors import error_response
from insightex.api.models import JobOut, job_out
from insightex.asr.languages import languages_for
from insightex.jobs import store

router = APIRouter(prefix="/api/jobs")

_NOT_FOUND = ("JOB_NOT_FOUND", "No job with that id.", 404)


def _read(request: Request, job_id: str) -> JobOut | None:
    try:
        settings = settings_of(request)
        return job_out(store.get_job(connection(settings), job_id), workspaces_of(request), languages_for(settings))
    except store.JobNotFound:
        return None


@router.get("", response_model=list[JobOut])
def list_jobs(request: Request, limit: int = 20, status: str | None = None):
    if status is not None and status not in store.JOB_STATUSES:
        return error_response("BAD_STATUS", f"status must be one of {', '.join(store.JOB_STATUSES)}", 400)
    settings = settings_of(request)
    jobs = store.list_jobs(connection(settings), max(1, min(limit, 200)), status)
    languages = languages_for(settings)
    return [job_out(j, workspaces_of(request), languages) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, request: Request):
    job = _read(request, job_id)
    return job if job is not None else error_response(*_NOT_FOUND)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, request: Request):
    conn = connection(settings_of(request))
    try:
        job = store.get_job(conn, job_id)
    except store.JobNotFound:
        return error_response(*_NOT_FOUND)
    if job.status in store.FINAL_STATUSES:
        return error_response("INVALID_STATE", f"The job is already {job.status}.", 409)
    store.request_cancel(conn, job_id)
    return _read(request, job_id)


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: str, request: Request):
    conn = connection(settings_of(request))
    try:
        store.retry(conn, job_id)
    except store.JobNotFound:
        return error_response(*_NOT_FOUND)
    except (store.InvalidJobState, store.PipelineMismatch) as exc:
        return error_response("INVALID_STATE", str(exc), 409)
    return _read(request, job_id)


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request):
    first = await run_in_threadpool(_read, request, job_id)
    if first is None:
        return error_response(*_NOT_FOUND)
    cfg = settings_of(request).api
    return StreamingResponse(
        _stream(request, job_id, first, cfg.sse_poll_interval_s, cfg.sse_keepalive_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _event(doc: JobOut) -> str:
    return f"event: status\ndata: {doc.model_dump_json()}\n\n"


async def _stream(request: Request, job_id: str, doc: JobOut | None, poll_s: float, keepalive_s: float) -> AsyncIterator[str]:
    """The worker is another process, so the database is the channel: poll, send on change, keepalive when quiet."""
    last_json: str | None = None
    last_sent = time.monotonic()
    while doc is not None:
        current = doc.model_dump_json()
        if current != last_json:
            last_json = current
            last_sent = time.monotonic()
            yield _event(doc)
        if doc.status in store.FINAL_STATUSES:
            return
        if time.monotonic() - last_sent >= keepalive_s:
            last_sent = time.monotonic()
            yield ": keepalive\n\n"
        await asyncio.sleep(poll_s)
        if await request.is_disconnected():
            return
        doc = await run_in_threadpool(_read, request, job_id)
