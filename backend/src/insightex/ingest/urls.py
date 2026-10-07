"""Classify a pasted URL (YouTube, Google Drive, direct), normalize it and derive its canonical id."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from insightex.core.ids import lecture_id_from_canonical
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings


YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{25,64}$")
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
YOUTU_BE_HOSTS = {"youtu.be", "www.youtu.be"}
DRIVE_HOSTS = {"drive.google.com"}
# Hosts we recognise but cannot ingest: other Google/YouTube properties and common LMSs.
_REJECTED_HOST_SUFFIXES = (
    "youtube.com", "youtu.be", "google.com", "googleusercontent.com",
    "instructure.com", "blackboard.com", "moodlecloud.com",
)
_MSG_LMS_OR_PAGE = (
    "This link isn't supported. Paste a YouTube video link, a Google Drive file link, or a direct "
    "link to a video file. For videos inside an LMS or course page, download the video and upload it instead."
)


@dataclass(frozen=True)
class ParsedUrl:
    source_type: str        # "youtube" | "gdrive" | "direct"
    source_url: str         # as pasted (whitespace stripped)
    normalized_url: str
    media_id: str           # YouTube video id, Drive file id, or url hash
    canonical_id: str

    @property
    def lecture_id(self) -> str:
        return lecture_id_from_canonical(self.canonical_id)

    @property
    def external_timestamp_url_template(self) -> str | None:
        if self.source_type == "youtube":
            return f"https://www.youtube.com/watch?v={self.media_id}&t={{t}}s"
        return None


def _unsupported(message: str | None = None) -> IngestError:
    return IngestError(ErrorCode.UNSUPPORTED_URL, message)


def _youtube(host: str, path_segments: list[str], query: dict[str, list[str]], raw: str) -> ParsedUrl:
    video_id = None
    if host in YOUTU_BE_HOSTS:
        if path_segments:
            video_id = path_segments[0]
    else:
        head = path_segments[0] if path_segments else ""
        if head == "watch":
            video_id = (query.get("v") or [None])[0]
        elif head in ("embed", "shorts", "live") and len(path_segments) >= 2:
            video_id = path_segments[1]
            if head == "embed" and video_id == "videoseries":
                video_id = None
        elif head == "playlist":
            raise IngestError(ErrorCode.PLAYLIST_NOT_SUPPORTED)
    if video_id is None:
        # list= without v= is a playlist; ignore list= only when a single video is named.
        if "list" in query:
            raise IngestError(ErrorCode.PLAYLIST_NOT_SUPPORTED)
        raise _unsupported(
            "This YouTube link doesn't point to a single video. Open the video and copy its link."
        )
    if not YOUTUBE_ID_RE.fullmatch(video_id):
        raise _unsupported("This YouTube link has an invalid video id.")
    return ParsedUrl(
        source_type="youtube",
        source_url=raw,
        normalized_url=f"https://www.youtube.com/watch?v={video_id}",
        media_id=video_id,
        canonical_id=f"yt:{video_id}",
    )


def _drive(path_segments: list[str], query: dict[str, list[str]], raw: str) -> ParsedUrl:
    file_id = None
    if len(path_segments) >= 3 and path_segments[0] == "file" and path_segments[1] == "d":
        if len(path_segments) == 3 or (len(path_segments) == 4 and path_segments[3] in ("view", "preview", "edit")):
            file_id = path_segments[2]
    elif path_segments in (["open"], ["uc"]):
        file_id = (query.get("id") or [None])[0]
    elif path_segments[:2] == ["drive", "folders"] or "folders" in path_segments:
        raise _unsupported("Google Drive folders aren't supported. Share and paste the link to a single video file.")
    if file_id is None:
        raise _unsupported("This Google Drive link doesn't point to a single file. Use the file's share link.")
    if not DRIVE_ID_RE.fullmatch(file_id):
        raise _unsupported("This Google Drive link has an invalid file id.")
    return ParsedUrl(
        source_type="gdrive",
        source_url=raw,
        normalized_url=f"https://drive.google.com/file/d/{file_id}/view",
        media_id=file_id,
        canonical_id=f"gdrive:{file_id}",
    )


def normalize_direct_url(parts) -> str:
    """Lowercase scheme and host, drop default port, userinfo-free, no fragment, sorted query."""
    scheme = parts.scheme.lower()
    host = parts.hostname.rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise _unsupported("This link has an invalid host name.") from exc
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port
    netloc = host if port is None or (scheme, port) in (("http", 80), ("https", 443)) else f"{host}:{port}"
    path = quote(unquote(parts.path or "/"), safe="/%:@!$&'()*+,;=~-._")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def parse_url(raw: str, max_length: int | None = None) -> ParsedUrl:
    if not isinstance(raw, str):
        raise _unsupported()
    raw = raw.strip()
    if max_length is None:
        max_length = IngestSettings.current().max_url_length
    if not raw or len(raw) > max_length or any(c.isspace() or ord(c) < 32 for c in raw):
        raise _unsupported()
    m = _SCHEME_RE.match(raw)
    if m is None or not raw[m.end():].startswith("//"):
        # "youtube.com/watch?v=..." pasted without a scheme; anything with another scheme is rejected.
        if m is not None and not re.match(r"^[A-Za-z0-9.-]+:\d+(/|$)", raw):
            raise _unsupported("Only http and https links are supported.")
        raw_for_parse = "https://" + raw
    else:
        if m.group(1).lower() not in ("http", "https"):
            raise _unsupported("Only http and https links are supported.")
        raw_for_parse = raw
    try:
        parts = urlsplit(raw_for_parse)
        _ = parts.port  # raises ValueError on a bad port
    except ValueError as exc:
        raise _unsupported() from exc
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or (("." not in host) and ":" not in host and host != "localhost"):
        raise _unsupported()
    if parts.username is not None or parts.password is not None:
        raise _unsupported("Links containing a username or password aren't supported.")

    path_segments = [s for s in parts.path.split("/") if s]
    query = parse_qs(parts.query)

    if host in YOUTUBE_HOSTS or host in YOUTU_BE_HOSTS:
        return _youtube(host, path_segments, query, raw)
    if host in DRIVE_HOSTS:
        return _drive(path_segments, query, raw)
    if any(host == s or host.endswith("." + s) for s in _REJECTED_HOST_SUFFIXES) or "moodle" in host:
        raise _unsupported(_MSG_LMS_OR_PAGE)

    normalized = normalize_direct_url(parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return ParsedUrl(
        source_type="direct",
        source_url=raw,
        normalized_url=normalized,
        media_id=digest,
        canonical_id=f"url:{digest}",
    )
