"""YouTube adapter (yt-dlp)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources import ytdlp
from insightex.ingest.sources.base import BytesCb, SourceMeta
from insightex.ingest.urls import ParsedUrl

_LIVE = {"is_live", "is_upcoming", "post_live"}
_LOGIN = {"private", "needs_auth", "subscriber_only", "premium_only"}


def meta_from_info(info: dict[str, Any]) -> SourceMeta:
    """Validate yt-dlp metadata (playlist, live, availability, age) and convert it."""
    if info.get("_type") in ("playlist", "multi_video"):
        raise IngestError(ErrorCode.PLAYLIST_NOT_SUPPORTED)
    if info.get("is_live") or info.get("live_status") in _LIVE:
        raise IngestError(ErrorCode.LIVE_NOT_SUPPORTED)
    if info.get("availability") in _LOGIN:
        raise IngestError(ErrorCode.PRIVATE_OR_LOGIN_REQUIRED)
    if (info.get("age_limit") or 0) >= 18:
        raise IngestError(ErrorCode.AGE_RESTRICTED)
    duration = info.get("duration")
    return SourceMeta(
        title=info.get("title"),
        uploader=info.get("uploader") or info.get("channel"),
        duration_s=float(duration) if duration else None,
        thumbnail_url=info.get("thumbnail"),
        size_bytes=ytdlp.selected_size(info),
        ext="mp4",
        extra={"live_status": info.get("live_status"), "availability": info.get("availability")},
    )


def probe(parsed: ParsedUrl, settings: IngestSettings) -> SourceMeta:
    info = ytdlp.extract_info(parsed.normalized_url, settings, "youtube")
    return meta_from_info(info)


def download(
    parsed: ParsedUrl, dest_dir: Path, settings: IngestSettings, meta: SourceMeta, on_bytes: BytesCb | None
) -> Path:
    return ytdlp.download(
        parsed.normalized_url, dest_dir, settings, "youtube", ytdlp.YOUTUBE_FORMAT, on_bytes, merge_mp4=True
    )
