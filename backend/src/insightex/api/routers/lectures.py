"""GET /api/lectures, /api/lectures/{id}, /api/lectures/{id}/video, /api/lectures/{id}/thumbnail."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from insightex.api.errors import error_response
from insightex.core import ids
from insightex.core.manifest import Manifest, read_manifest
from insightex.ingest.engine import THUMB_NAME, VIDEO_NAME

router = APIRouter(prefix="/api/lectures")

_NOT_FOUND = ("LECTURE_NOT_FOUND", "This lecture isn't in your library.", 404)


def _ready_manifest(request: Request, lecture_id: str) -> tuple[Path, Manifest] | None:
    """Directory and manifest of a ready lecture, or None. Never builds a path from an unvalidated id."""
    try:
        path = ids.lecture_dir(request.app.state.settings.lectures_dir, lecture_id)
    except ValueError:
        return None
    manifest = read_manifest(path)
    if manifest is None or manifest.status != "ready":
        return None
    return path, manifest


def _public(manifest: Manifest) -> dict:
    """The manifest as the UI sees it: file names stay relative, plus URLs for the media endpoints."""
    data = manifest.to_dict()
    lid = manifest.lecture_id
    files = manifest.files or {}
    data["video_url"] = f"/api/lectures/{lid}/video" if files.get("video") else None
    data["thumbnail_url"] = f"/api/lectures/{lid}/thumbnail" if files.get("thumbnail") else None
    return data


@router.get("")
def list_lectures(request: Request):
    root = Path(request.app.state.settings.lectures_dir)
    items = []
    if root.is_dir():
        for entry in root.iterdir():
            if not entry.is_dir() or not ids.LECTURE_ID_RE.fullmatch(entry.name):
                continue
            found = _ready_manifest(request, entry.name)
            if found is None:
                continue
            _, m = found
            items.append({
                "lecture_id": m.lecture_id,
                "title": m.title,
                "duration_s": m.duration_s,
                "thumbnail_url": _public(m)["thumbnail_url"],
                "created_at": m.created_at,
            })
    items.sort(key=lambda i: i["created_at"], reverse=True)
    return {"lectures": items}


@router.get("/{lecture_id}")
def get_lecture(lecture_id: str, request: Request):
    found = _ready_manifest(request, lecture_id)
    if found is None:
        return error_response(*_NOT_FOUND)
    return _public(found[1])


def _media(request: Request, lecture_id: str, key: str, name: str, media_type: str):
    found = _ready_manifest(request, lecture_id)
    if found is None:
        return error_response(*_NOT_FOUND)
    path, manifest = found
    if not (manifest.files or {}).get(key):
        return error_response(*_NOT_FOUND)
    file = path / name  # fixed file name, never taken from the request
    if not file.is_file():
        return error_response(*_NOT_FOUND)
    # Starlette's FileResponse serves Range requests (206, Content-Range, 416) and sets Accept-Ranges.
    return FileResponse(file, media_type=media_type)


@router.api_route("/{lecture_id}/video", methods=["GET", "HEAD"])
def get_video(lecture_id: str, request: Request):
    return _media(request, lecture_id, "video", VIDEO_NAME, "video/mp4")


@router.api_route("/{lecture_id}/thumbnail", methods=["GET", "HEAD"])
def get_thumbnail(lecture_id: str, request: Request):
    return _media(request, lecture_id, "thumbnail", THUMB_NAME, "image/jpeg")
