"""POST /api/ingest/probe, /link and /upload; GET /api/ingest/limits.

The upload is a raw streamed request body (not multipart): it is read in chunks, written to the staging
area and hashed in a worker thread, and handed to `enqueue_staged`, the same function the CLI ends in.
"""

from __future__ import annotations

import logging
import threading
from typing import Any
from urllib.parse import unquote

import anyio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from insightex.api.deps import connection, settings_of, workspaces_of
from insightex.api.errors import error_response, ingest_error_response
from insightex.api.models import LinkAccepted, UploadAccepted
from insightex.ingest import probe as probe_mod
from insightex.ingest import staging
from insightex.ingest.errors import DEFAULT_MESSAGES, ErrorCode, IngestError, IngestRejected
from insightex.ingest.file_jobs import enqueue_staged
from insightex.ingest.link_jobs import enqueue_link
from insightex.media import engine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest")


class ProbeBody(BaseModel):
    url: str


class LinkBody(BaseModel):
    url: str
    rights_confirmed: Any = False  # anything but the JSON value true is a 400, not a 422


@router.post("/probe")
def probe(body: ProbeBody, request: Request):
    # Sync handler: FastAPI runs it in a thread, so a slow probe does not block the server.
    try:
        result = probe_mod.probe(body.url, request.app.state.ingest_settings, workspaces_of(request)).to_dict()
    except IngestError as exc:
        return ingest_error_response(exc)
    except Exception:
        log.exception("unexpected error probing a link")
        return error_response(ErrorCode.NETWORK_ERROR, DEFAULT_MESSAGES[ErrorCode.NETWORK_ERROR], 502)
    if result["exists_locally"]:
        result["thumbnail_url"] = f"/api/lectures/{result['workspace_id']}/thumbnail"
    return result


@router.post("/link", status_code=202, response_model=LinkAccepted)
def ingest_link(body: LinkBody, request: Request):
    if body.rights_confirmed is not True:
        return ingest_error_response(IngestError(ErrorCode.RIGHTS_NOT_CONFIRMED))
    settings = settings_of(request)
    try:
        job_id, workspace_id, deduplicated = enqueue_link(connection(settings), settings, body.url)
    except IngestError as exc:
        return ingest_error_response(exc)
    return LinkAccepted(job_id=job_id, workspace_id=workspace_id, deduplicated=deduplicated)


# -- upload ------------------------------------------------------------------------------------------

_STATUS = {
    ErrorCode.RIGHTS_NOT_CONFIRMED: 400,
    ErrorCode.LENGTH_REQUIRED: 411,
    ErrorCode.EMPTY_FILE: 400,
    ErrorCode.TOO_LARGE: 413,
    ErrorCode.UPLOAD_BUSY: 409,
    ErrorCode.INSUFFICIENT_DISK: 507,
    ErrorCode.UPLOAD_INTERRUPTED: 400,
}
_upload_slot = threading.Lock()  # one upload at a time; held from the busy check until every exit path has cleaned up


def _refuse(code: ErrorCode, details: str = ""):
    if details:
        log.warning("upload refused: %s (%s)", code, details)
    response = error_response(code, DEFAULT_MESSAGES[code], _STATUS[code])
    response.headers["Connection"] = "close"  # the body was not read: do not keep the connection for reuse
    return response


@router.get("/limits")
def limits(request: Request):
    """What the upload form needs to check a file before sending it."""
    return {"max_upload_bytes": request.app.state.ingest_settings.max_download_bytes}


@router.post("/upload", status_code=202, response_model=UploadAccepted)
async def upload(request: Request):
    """Receive a video as the raw request body and queue its ingest. Checks run before any body byte is read."""
    settings = settings_of(request)
    cfg = request.app.state.ingest_settings
    if request.headers.get("x-insightex-rights-confirmed", "").strip() != "true":
        return _refuse(ErrorCode.RIGHTS_NOT_CONFIRMED)
    raw_length = request.headers.get("content-length", "").strip()
    if not raw_length.isascii() or not raw_length.isdigit():
        return _refuse(ErrorCode.LENGTH_REQUIRED)
    length = int(raw_length)
    try:
        engine.check_size(length, cfg.max_download_bytes)
    except IngestRejected as exc:
        return _refuse(exc.code, exc.details)
    if not _upload_slot.acquire(blocking=False):
        return _refuse(ErrorCode.UPLOAD_BUSY)
    staged_upload: staging.StagedUpload | None = None
    try:
        directory = staging.staging_dir(settings)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            engine.check_disk(length, directory, cfg)
        except IngestRejected as exc:
            return _refuse(exc.code, exc.details)
        filename = unquote(request.headers.get("x-insightex-filename", ""))
        staged_upload = await anyio.to_thread.run_sync(staging.StagedUpload, settings)
        received = await _receive(request, staged_upload, length, settings.ingest.file.copy_chunk_bytes)
        if received is None:
            return _refuse(ErrorCode.UPLOAD_INTERRUPTED)
        staged = await anyio.to_thread.run_sync(staged_upload.finish)
        staged_upload = None  # now owned by enqueue_staged (the job, or deleted as a duplicate)
        result = await anyio.to_thread.run_sync(_enqueue, settings, staged, filename)
    except Exception:
        log.exception("upload failed unexpectedly")
        return error_response("INTERNAL_ERROR", "The upload couldn't be processed. Please try again.", 500)
    finally:
        if staged_upload is not None:
            await anyio.to_thread.run_sync(staged_upload.abort)
        _upload_slot.release()
    body = {"lecture_id": result.workspace_id, "job_id": result.job_id, "deduplicated": result.deduplicated}
    return JSONResponse(body, status_code=200 if result.job_id is None else 202)


def _enqueue(settings, staged, filename: str):
    return enqueue_staged(connection(settings), settings, staged, via="http", original_filename=filename)


async def _receive(request: Request, target: staging.StagedUpload, length: int, flush_bytes: int) -> int | None:
    """Stream the body into `target`. Returns the byte count, or None when it was cut short or too long.

    Chunks are gathered up to `flush_bytes` before the (blocking) write and hash go to a worker thread, so the
    event loop stays free for other requests, such as the job's SSE stream. The body is never held whole.
    """
    pending: list[bytes] = []
    pending_bytes = 0
    total = 0

    async def flush() -> None:
        nonlocal pending, pending_bytes
        block = b"".join(pending)
        pending, pending_bytes = [], 0
        await anyio.to_thread.run_sync(target.write, block)

    stream = request.stream().__aiter__()
    while True:
        try:
            chunk = await stream.__anext__()
        except StopAsyncIteration:
            break
        except Exception as exc:  # noqa: BLE001 - a body that cannot be read to the end is an interrupted upload
            log.warning("upload interrupted after %d of %d bytes: %s: %s", total, length, type(exc).__name__, exc)
            return None
        total += len(chunk)
        if total > length:
            log.warning("upload interrupted: more bytes than Content-Length (%d)", length)
            return None
        pending.append(chunk)
        pending_bytes += len(chunk)
        if pending_bytes >= flush_bytes:
            await flush()
    if pending:
        await flush()
    if total != length:
        log.warning("upload interrupted: body ended after %d of %d bytes", total, length)
        return None
    return total
