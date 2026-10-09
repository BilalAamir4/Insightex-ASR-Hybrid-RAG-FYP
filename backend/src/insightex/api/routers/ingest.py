"""POST /api/ingest/probe and POST /api/ingest/link."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from insightex.api.deps import connection, settings_of, workspaces_of
from insightex.api.errors import error_response, ingest_error_response
from insightex.api.models import LinkAccepted
from insightex.ingest import probe as probe_mod
from insightex.ingest.errors import DEFAULT_MESSAGES, ErrorCode, IngestError
from insightex.ingest.link_jobs import enqueue_link

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
