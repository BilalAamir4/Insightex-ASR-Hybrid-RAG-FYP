"""Direct video URLs: streamed with httpx behind the SSRF guard, size-capped on header and on bytes."""

from __future__ import annotations

import logging
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from urllib.parse import unquote, urlsplit

import httpx

from insightex.ingest import netguard
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources.base import BytesCb, SourceMeta
from insightex.ingest.sources.ytdlp import too_large_message
from insightex.ingest.urls import ParsedUrl

log = logging.getLogger(__name__)

VIDEO_EXTS = {
    "mp4", "m4v", "mov", "mkv", "webm", "avi", "flv", "wmv", "mpg", "mpeg",
    "ts", "m2ts", "mts", "3gp", "ogv",
}
_GENERIC_TYPES = {"application/octet-stream", "binary/octet-stream", "application/x-download", "application/download"}
_STREAMING_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl", "application/dash+xml"}
CHUNK = 1024 * 1024

_MSG_PAGE = (
    "This link opens a web page, not a video file. Paste a direct link to the video file, "
    "or download the video and upload it instead."
)


def _ext_from_url(url: str) -> str | None:
    suffix = PurePosixPath(unquote(urlsplit(url).path)).suffix.lower().lstrip(".")
    return suffix or None


def _filename(response: httpx.Response) -> str | None:
    cd = response.headers.get("content-disposition") or ""
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
    if m:
        return unquote(m.group(1).strip()) or None
    name = PurePosixPath(unquote(urlsplit(str(response.url)).path)).name
    return name or None


def check_response(response: httpx.Response, settings: IngestSettings) -> SourceMeta:
    """Validate status, Content-Type and Content-Length of a (streamed) response."""
    if response.status_code >= 400:
        raise netguard.map_http_status(response.status_code)
    ctype = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    name = _filename(response)
    ext = (PurePosixPath(name).suffix.lower().lstrip(".") if name else None) or _ext_from_url(str(response.url))
    if ctype in _STREAMING_TYPES or ext in ("m3u8", "mpd"):
        raise IngestError(ErrorCode.NOT_A_VIDEO, "Streaming playlists (HLS/DASH) aren't supported. Use a link to a video file.")
    is_video = ctype.startswith("video/") or ctype == "application/mp4" or (
        (not ctype or ctype in _GENERIC_TYPES) and ext in VIDEO_EXTS
    )
    if not is_video:
        msg = _MSG_PAGE if ctype in ("text/html", "application/xhtml+xml") else None
        raise IngestError(ErrorCode.NOT_A_VIDEO, msg)
    length = response.headers.get("content-length")
    size = int(length) if length and length.isdigit() else None
    if size is not None and size > settings.max_download_bytes:
        raise IngestError(ErrorCode.TOO_LARGE, too_large_message(settings.max_download_bytes))
    if ext not in VIDEO_EXTS:
        ext = (mimetypes.guess_extension(ctype) or ".bin").lstrip(".") if ctype.startswith("video/") else "bin"
    title = PurePosixPath(name).stem if name else None
    return SourceMeta(title=title, size_bytes=size, ext=ext, extra={"content_type": ctype})


def probe(
    parsed: ParsedUrl,
    settings: IngestSettings,
    client: httpx.Client | None = None,
    resolver: netguard.Resolver = netguard.system_resolver,
) -> SourceMeta:
    """Headers only: the body is never read. Duration is unknown until the file is downloaded."""
    own = client is None
    client = client or netguard.make_client()
    try:
        with netguard.guarded_stream(client, parsed.source_url, resolver) as response:
            return check_response(response, settings)
    except IngestError:
        raise
    except httpx.HTTPError as exc:
        log.warning("direct probe failed for %s: %r", parsed.normalized_url, exc)
        raise netguard.map_httpx_error(exc) from exc
    finally:
        if own:
            client.close()


def download(
    parsed: ParsedUrl,
    dest_dir: Path,
    settings: IngestSettings,
    meta: SourceMeta,
    on_bytes: BytesCb | None,
    client: httpx.Client | None = None,
    resolver: netguard.Resolver = netguard.system_resolver,
    wrap_output: Callable[[BinaryIO], BinaryIO] | None = None,
) -> Path:
    """Stream the file into dest_dir. `wrap_output(file)` may return a writer that sees every byte (hashing)."""
    cap = settings.max_download_bytes
    own = client is None
    client = client or netguard.make_client()
    part = dest_dir / "source.part"
    try:
        with netguard.guarded_stream(client, parsed.source_url, resolver) as response:
            checked = check_response(response, settings)  # headers re-checked: the server may have changed
            out = dest_dir / f"source.{checked.ext or 'bin'}"
            received = 0
            with part.open("wb") as raw:
                f = wrap_output(raw) if wrap_output else raw
                for chunk in response.iter_bytes(CHUNK):
                    received += len(chunk)
                    if received > cap:
                        raise IngestError(ErrorCode.TOO_LARGE, too_large_message(cap))
                    f.write(chunk)
                    if on_bytes:
                        on_bytes(received, checked.size_bytes)
            if checked.size_bytes is not None and received != checked.size_bytes:
                raise IngestError(ErrorCode.NETWORK_ERROR, "The download was cut off before it finished. Try again.")
        part.replace(out)
        return out
    except IngestError:
        part.unlink(missing_ok=True)
        raise
    except httpx.HTTPError as exc:
        part.unlink(missing_ok=True)
        log.warning("direct download failed for %s: %r", parsed.normalized_url, exc)
        raise netguard.map_httpx_error(exc) from exc
    finally:
        if own:
            client.close()
