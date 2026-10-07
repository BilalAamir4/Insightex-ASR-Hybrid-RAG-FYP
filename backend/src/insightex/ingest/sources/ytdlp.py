"""yt-dlp through its Python API: shared options, metadata extraction, download and error mapping.

Never uses cookies, netrc or any login: only publicly viewable media can be ingested.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError, YoutubeDLError

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources.base import BytesCb

log = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

def youtube_format(max_height: int) -> str:
    # H.264 <=max_height + AAC (merged into mp4), then any single-file H.264+AAC <=max_height,
    # then the best <=max_height of any codec, then whatever exists (transcode scales it down).
    h = f"[height<={max_height}]"
    return f"bv*[vcodec^=avc1]{h}+ba[acodec^=mp4a]/b[vcodec^=avc1][acodec^=mp4a]{h}/bv*{h}+ba/b{h}/bv*+ba/b"


class _SizeCapExceeded(Exception):
    def __init__(self, received: int) -> None:
        super().__init__(f"received {received} bytes")
        self.received = received


class _Logger:
    """Routes yt-dlp output to logging and keeps messages for error-code mapping. Info-level lines are
    kept too: yt-dlp reports a skipped over-size download ("larger than max-filesize") only there."""

    MAX_KEPT = 200

    def __init__(self) -> None:
        self.messages: list[str] = []

    def _keep(self, msg: str) -> None:
        if not msg.startswith("[debug]") and len(self.messages) < self.MAX_KEPT:
            self.messages.append(msg)

    def debug(self, msg: str) -> None:
        self._keep(msg)
        log.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        self._keep(msg)
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        self.messages.append(msg)
        log.info("yt-dlp warning: %s", msg)

    def error(self, msg: str) -> None:
        self.messages.append(msg)
        log.warning("yt-dlp error: %s", msg)


def deno_path(settings: IngestSettings) -> str | None:
    if settings.deno_path:
        return settings.deno_path
    try:
        import deno  # the PyPI wheel, venv-local

        return str(deno.find_deno_bin())
    except Exception:  # noqa: BLE001 - fall back to PATH
        return shutil.which("deno")


def base_opts(settings: IngestSettings, logger: _Logger) -> dict[str, Any]:
    deno = deno_path(settings)
    if deno is None:
        log.warning("no deno binary found; YouTube downloads will likely fail")
    return {
        "logger": logger,
        "quiet": True,
        "noprogress": True,
        "color": {"stdout": "no_color", "stderr": "no_color"},
        "noplaylist": True,
        "cookiefile": None,
        "cookiesfrombrowser": None,
        "usenetrc": False,
        "js_runtimes": {"deno": {"path": deno} if deno else {}},
        "socket_timeout": settings.socket_timeout_s,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "check_formats": False,
    }


def extract_info(url: str, settings: IngestSettings, source_type: str) -> dict[str, Any]:
    logger = _Logger()
    try:
        with yt_dlp.YoutubeDL(base_opts(settings, logger)) as ydl:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)
    except (YoutubeDLError, OSError) as exc:
        log.warning("yt-dlp extract failed for %s: %r; messages=%s", url, exc, logger.messages)
        raise map_ytdlp_error(exc, logger.messages, source_type) from exc


def selected_size(info: dict[str, Any]) -> int | None:
    """Expected bytes for the selected format(s), from filesize or filesize_approx."""
    formats = info.get("requested_formats") or ([info] if info.get("format_id") else [])
    total = 0
    for f in formats:
        size = f.get("filesize") or f.get("filesize_approx")
        if not size:
            return None
        total += int(size)
    return total or None


def download(
    url: str,
    dest_dir: Path,
    settings: IngestSettings,
    source_type: str,
    fmt: str,
    on_bytes: BytesCb | None = None,
    merge_mp4: bool = True,
) -> Path:
    """Download url into dest_dir as source.<ext>; returns the final file path."""
    logger = _Logger()
    cap = settings.max_download_bytes
    seen: dict[str, tuple[int, int | None]] = {}
    expected: dict[str, int | None] = {"total": None}

    def hook(d: dict[str, Any]) -> None:
        if d.get("status") not in ("downloading", "finished"):
            return
        name = d.get("filename") or d.get("tmpfilename") or "?"
        got = int(d.get("downloaded_bytes") or 0)
        tot = d.get("total_bytes") or d.get("total_bytes_estimate")
        seen[name] = (got, int(tot) if tot else None)
        received = sum(v[0] for v in seen.values())
        if received > cap:
            raise _SizeCapExceeded(received)
        if on_bytes:
            total = expected["total"]
            if total is None and all(v[1] for v in seen.values()):
                total = sum(v[1] for v in seen.values())  # type: ignore[misc]
            on_bytes(received, total)

    opts = base_opts(settings, logger) | {
        "format": fmt,
        "outtmpl": {"default": str(dest_dir / "source.%(ext)s")},
        "progress_hooks": [hook],
        "max_filesize": cap,
        "overwrites": True,
        "continuedl": False,
        "writethumbnail": False,
        "writesubtitles": False,
    }
    if merge_mp4:
        opts["merge_output_format"] = "mp4"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            size = selected_size(info)
            if size is not None and size > cap:
                raise IngestError(ErrorCode.TOO_LARGE, too_large_message(cap))
            expected["total"] = size
            info = ydl.process_ie_result(info, download=True)
    except IngestError:
        raise
    except _SizeCapExceeded as exc:
        log.warning("download of %s exceeded %d bytes (%d received)", url, cap, exc.received)
        raise IngestError(ErrorCode.TOO_LARGE, too_large_message(cap)) from exc
    except (YoutubeDLError, OSError) as exc:
        cause = getattr(exc, "exc_info", None)
        if cause and isinstance(cause[1], _SizeCapExceeded):
            raise IngestError(ErrorCode.TOO_LARGE, too_large_message(cap)) from exc
        log.warning("yt-dlp download failed for %s: %r; messages=%s", url, exc, logger.messages)
        raise map_ytdlp_error(exc, logger.messages, source_type) from exc

    paths = [Path(d["filepath"]) for d in info.get("requested_downloads") or [] if d.get("filepath")]
    paths = [p for p in paths if p.is_file()]
    if not paths:
        text = " ".join(logger.messages).lower()
        if "max-filesize" in text or "max_filesize" in text:
            raise IngestError(ErrorCode.TOO_LARGE, too_large_message(cap))
        log.warning("yt-dlp produced no file for %s; messages=%s", url, logger.messages)
        raise IngestError(ErrorCode.DOWNLOAD_FAILED)
    if paths[0].stat().st_size > cap:
        raise IngestError(ErrorCode.TOO_LARGE, too_large_message(cap))
    return paths[0]


def too_large_message(cap: int) -> str:
    return f"This video file is larger than the {cap / 1024**3:.0f} GB limit."


def map_ytdlp_error(exc: BaseException, messages: list[str] | None = None, source_type: str = "youtube") -> IngestError:
    """Map a yt-dlp exception (plus logged warnings) onto an error code. Order matters."""
    cause = getattr(exc, "exc_info", None)
    inner = cause[1] if cause and len(cause) > 1 else None
    if isinstance(exc, GeoRestrictedError) or isinstance(inner, GeoRestrictedError):
        return IngestError(ErrorCode.GEO_BLOCKED)
    text = _ANSI_RE.sub("", " ".join([str(exc), str(inner or ""), *(messages or [])])).lower()

    def has(*needles: str) -> bool:
        return any(n in text for n in needles)

    if has("available in your country", "geo restrict", "geo-restrict", "from your location", "in your region"):
        return IngestError(ErrorCode.GEO_BLOCKED)
    if has("drm"):
        return IngestError(ErrorCode.UNSUPPORTED_URL, "This video is copy-protected (DRM) and can't be added.")
    if has("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"):
        return IngestError(ErrorCode.AGE_RESTRICTED)
    if has("not a bot", "captcha"):
        return IngestError(
            ErrorCode.DOWNLOAD_FAILED,
            "YouTube is temporarily refusing downloads from this server. Try again later.",
        )
    if has("live event will begin", "premieres in", "premiere will begin", "this live event", "is live",
           "live stream recording is not available", "is_upcoming"):
        return IngestError(ErrorCode.LIVE_NOT_SUPPORTED)
    if source_type == "gdrive":
        if has("quota", "too many users", "rate limit"):
            return IngestError(ErrorCode.DRIVE_QUOTA_EXCEEDED)
        if has("http error 401", "http error 403", "http error 404", "you need access", "access denied",
               "permission", "sign in"):
            return IngestError(ErrorCode.DRIVE_NOT_SHARED)
    if has("members-only", "join this channel", "private video", "sign in", "login required",
           "requires authentication", "premium", "this video is private"):
        return IngestError(ErrorCode.PRIVATE_OR_LOGIN_REQUIRED)
    if has("max-filesize", "max_filesize"):
        return IngestError(ErrorCode.TOO_LARGE)
    if has("video unavailable", "has been removed", "no longer available", "does not exist",
           "http error 404", "http error 410"):
        return IngestError(ErrorCode.DOWNLOAD_FAILED, "This video is unavailable. It may have been removed.")
    if has("unsupported url"):
        return IngestError(ErrorCode.UNSUPPORTED_URL)
    if has("requested format is not available", "no video formats"):
        return IngestError(ErrorCode.DOWNLOAD_FAILED, "No downloadable version of this video was found.")
    if has("timed out", "timeout", "unable to download webpage", "connection", "name or service not known",
           "temporary failure in name resolution", "network is unreachable", "urlopen error", "ssl",
           "remote end closed", "incompleteread", "transporterror"):
        return IngestError(ErrorCode.NETWORK_ERROR)
    if isinstance(exc, (DownloadError, ExtractorError, YoutubeDLError)):
        return IngestError(ErrorCode.DOWNLOAD_FAILED)
    return IngestError(ErrorCode.DOWNLOAD_FAILED)
