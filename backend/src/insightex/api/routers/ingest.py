"""POST /api/ingest/probe, POST /api/ingest, GET /api/ingest/{job_id}."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, StrictBool

from insightex.api.errors import error_response, ingest_error_response
from insightex.ingest import engine
from insightex.ingest.errors import DEFAULT_MESSAGES, ErrorCode, IngestError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest")


class ProbeBody(BaseModel):
    url: str


class IngestBody(BaseModel):
    url: str
    rights_confirmed: StrictBool = False


@router.post("/probe")
def probe(body: ProbeBody, request: Request):
    # Sync handler: FastAPI runs it in a thread, so a slow probe does not block the server.
    try:
        result = engine.probe(body.url, settings=request.app.state.settings).to_dict()
    except IngestError as exc:
        return ingest_error_response(exc)
    except Exception:
        log.exception("unexpected error probing a link")
        return error_response(ErrorCode.NETWORK_ERROR, DEFAULT_MESSAGES[ErrorCode.NETWORK_ERROR], 502)
    if result["exists_locally"]:
        result["thumbnail_url"] = f"/api/lectures/{result['lecture_id']}/thumbnail"
    return result


@router.post("")
def start_ingest(body: IngestBody, request: Request):
    if body.rights_confirmed is not True:
        return ingest_error_response(IngestError(ErrorCode.RIGHTS_NOT_CONFIRMED))
    try:
        job_id, lecture_id = request.app.state.jobs.submit(body.url)
    except IngestError as exc:
        return ingest_error_response(exc)
    return {"job_id": job_id, "lecture_id": lecture_id, "status": "ready" if job_id is None else "queued"}


@router.get("/{job_id}")
def job_status(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if job is None:
        return error_response("JOB_NOT_FOUND", "This job is no longer tracked. Check the library.", 404)
    return job
