"""Google Drive adapter. Metadata always comes from yt-dlp; the download backend is configurable
(ingest.url.drive_downloader: yt-dlp | gdown)."""

from __future__ import annotations

import logging
from pathlib import Path

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources import ytdlp
from insightex.ingest.sources.base import BytesCb, SourceMeta
from insightex.ingest.urls import ParsedUrl

log = logging.getLogger(__name__)

# The original uploaded file ("source"), not one of Drive's re-encoded playback streams.
DRIVE_FORMAT = "source/bv*+ba/b"


def probe(parsed: ParsedUrl, settings: IngestSettings) -> SourceMeta:
    info = ytdlp.extract_info(parsed.normalized_url, settings, "gdrive")
    duration = info.get("duration")
    source = next((f for f in info.get("formats") or [] if f.get("format_id") == "source"), None)
    return SourceMeta(
        title=info.get("title"),
        uploader=None,
        duration_s=float(duration) if duration else None,
        thumbnail_url=info.get("thumbnail"),
        size_bytes=(source or {}).get("filesize"),
        ext=(source or {}).get("ext") or info.get("ext"),
        extra={"has_source_format": source is not None},
    )


def download(
    parsed: ParsedUrl, dest_dir: Path, settings: IngestSettings, meta: SourceMeta, on_bytes: BytesCb | None
) -> Path:
    if settings.drive_downloader == "gdown":
        return _download_gdown(parsed, dest_dir, settings, meta, on_bytes)
    return ytdlp.download(
        parsed.normalized_url, dest_dir, settings, "gdrive", DRIVE_FORMAT, on_bytes, merge_mp4=False
    )


class _GdownSizeCap(Exception):
    pass


def _download_gdown(
    parsed: ParsedUrl, dest_dir: Path, settings: IngestSettings, meta: SourceMeta, on_bytes: BytesCb | None
) -> Path:
    import gdown

    cap = settings.max_download_bytes
    out = dest_dir / f"source.{meta.ext or 'bin'}"

    def progress(received: int, total: int | None) -> None:
        if (total and total > cap) or received > cap:
            raise _GdownSizeCap()
        if on_bytes:
            on_bytes(received, total)

    try:
        gdown.download(
            id=parsed.media_id, output=str(out), quiet=True, use_cookies=False,
            progress=progress, timeout=(15, 60),
        )
    except _GdownSizeCap as exc:
        raise IngestError(ErrorCode.TOO_LARGE, ytdlp.too_large_message(cap)) from exc
    except Exception as exc:  # noqa: BLE001 - every gdown/requests failure is mapped
        log.warning("gdown failed for %s: %r", parsed.media_id, exc)
        raise map_gdown_error(exc) from exc
    if not out.is_file():
        raise IngestError(ErrorCode.DOWNLOAD_FAILED)
    return out


def map_gdown_error(exc: BaseException) -> IngestError:
    import requests
    from gdown.exceptions import DownloadError, FileURLRetrievalError

    text = str(exc).lower()
    if isinstance(exc, FileURLRetrievalError):
        if "too many users" in text or "quota" in text:
            return IngestError(ErrorCode.DRIVE_QUOTA_EXCEEDED)
        return IngestError(ErrorCode.DRIVE_NOT_SHARED)
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403, 404):
            return IngestError(ErrorCode.DRIVE_NOT_SHARED)
        if status == 429:
            return IngestError(ErrorCode.DRIVE_QUOTA_EXCEEDED)
        return IngestError(ErrorCode.DOWNLOAD_FAILED)
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return IngestError(ErrorCode.NETWORK_ERROR)
    if isinstance(exc, DownloadError):
        return IngestError(ErrorCode.DOWNLOAD_FAILED)
    return IngestError(ErrorCode.DOWNLOAD_FAILED)
