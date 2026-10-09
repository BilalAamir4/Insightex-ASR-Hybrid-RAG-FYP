"""The library: GET /api/lectures, /api/lectures/{id}, /{id}/video, /{id}/thumbnail; DELETE /api/lectures/{id}.

A lecture is a workspace whose `normalise` stage is complete. Files are found through the workspace
manifest (`Workspaces.stage_output_dir`), never by a path built from the request.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response

from insightex.api.deps import connection, settings_of, workspaces_of
from insightex.api.errors import error_response
from insightex.api.models import LectureItem, LectureList, LectureOut
from insightex.ingest.pipeline import NORMALISE_JSON, SOURCE_JSON, THUMB_NAME, VIDEO_NAME
from insightex.jobs import cache
from insightex.jobs.workspace import Workspaces, validate_workspace_id

router = APIRouter(prefix="/api/lectures")

_NOT_FOUND = ("LECTURE_NOT_FOUND", "This lecture isn't in your library.", 404)


def _json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _lecture_dir(workspaces: Workspaces, lecture_id: str) -> Path | None:
    """The completed `normalise` directory of a ready lecture, or None. Rejects ids that are not one path component."""
    try:
        validate_workspace_id(lecture_id)
        directory = workspaces.stage_output_dir(lecture_id, "normalise")
    except ValueError:
        return None
    return directory if directory is not None and (directory / VIDEO_NAME).is_file() else None


def _item(workspaces: Workspaces, lecture_id: str, normalised: Path, created_at: str | None) -> LectureItem:
    fetched = workspaces.stage_output_dir(lecture_id, "fetch")
    source = _json(fetched / SOURCE_JSON) if fetched else {}
    info = _json(normalised / NORMALISE_JSON)
    return LectureItem(
        lecture_id=lecture_id,
        title=source.get("title"),
        duration_s=info.get("duration_s") or source.get("duration_s"),
        thumbnail_url=f"/api/lectures/{lecture_id}/thumbnail" if (normalised / THUMB_NAME).is_file() else None,
        created_at=created_at,
    )


@router.get("", response_model=LectureList)
def list_lectures(request: Request):
    workspaces = workspaces_of(request)
    items = []
    for row in cache.list_workspaces(connection(settings_of(request)), workspaces):
        directory = _lecture_dir(workspaces, row["id"])
        if directory is not None:
            items.append(_item(workspaces, row["id"], directory, row["created_at"]))
    items.sort(key=lambda i: i.created_at or "", reverse=True)
    return LectureList(lectures=items)


@router.get("/{lecture_id}", response_model=LectureOut)
def get_lecture(lecture_id: str, request: Request):
    workspaces = workspaces_of(request)
    directory = _lecture_dir(workspaces, lecture_id)
    if directory is None:
        return error_response(*_NOT_FOUND)
    row = connection(settings_of(request)).execute("SELECT created_at FROM workspaces WHERE id = ?", (lecture_id,)).fetchone()
    item = _item(workspaces, lecture_id, directory, row["created_at"] if row else None)
    fetched = workspaces.stage_output_dir(lecture_id, "fetch")
    template = _json(fetched / SOURCE_JSON).get("external_timestamp_url_template") if fetched else None
    warnings = _json(directory / NORMALISE_JSON).get("warnings")
    return LectureOut(**item.model_dump(), video_url=f"/api/lectures/{lecture_id}/video",
                      warnings=warnings if isinstance(warnings, list) else [],
                      external_timestamp_url_template=template)


def _touch(request: Request, lecture_id: str) -> None:
    """Record access for the cache, at most once per `api.touch_min_interval_s` per workspace (in memory)."""
    state = request.app.state
    now = time.monotonic()
    with state.touch_lock:
        last = state.touch_times.get(lecture_id)
        if last is not None and now - last < settings_of(request).api.touch_min_interval_s:
            return
        state.touch_times[lecture_id] = now
    cache.touch(connection(settings_of(request)), lecture_id)


def _media(request: Request, lecture_id: str, name: str, media_type: str):
    directory = _lecture_dir(workspaces_of(request), lecture_id)
    if directory is None or not (directory / name).is_file():  # fixed file names, never taken from the request
        return error_response(*_NOT_FOUND)
    _touch(request, lecture_id)
    # Starlette's FileResponse serves Range requests (206, Content-Range, 416) and sets Accept-Ranges.
    return FileResponse(directory / name, media_type=media_type)


@router.api_route("/{lecture_id}/video", methods=["GET", "HEAD"])
def get_video(lecture_id: str, request: Request):
    return _media(request, lecture_id, VIDEO_NAME, "video/mp4")


@router.api_route("/{lecture_id}/thumbnail", methods=["GET", "HEAD"])
def get_thumbnail(lecture_id: str, request: Request):
    return _media(request, lecture_id, THUMB_NAME, "image/jpeg")


@router.delete("/{lecture_id}", status_code=204)
def delete_lecture(lecture_id: str, request: Request):
    try:
        cache.delete(connection(settings_of(request)), workspaces_of(request), lecture_id)
    except (cache.WorkspaceNotFound, ValueError):
        return error_response(*_NOT_FOUND)
    except cache.WorkspaceBusy:
        return error_response("LECTURE_BUSY", "This lecture is still being processed. Cancel the job first.", 409)
    request.app.state.touch_times.pop(lecture_id, None)
    return Response(status_code=204)
