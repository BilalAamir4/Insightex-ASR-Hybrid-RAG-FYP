"""Source identity: the workspace id for a YouTube link or for a file's bytes (ADR-0034)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs, urlsplit

from insightex.jobs.workspace import validate_workspace_id

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com"}
_PATH_PREFIXES = ("shorts", "embed", "live")


def youtube_video_id(url: str) -> str | None:
    """The 11-character video id of a YouTube URL, or None.

    Accepts watch?v=, youtu.be/, /shorts/, /embed/ and /live/ on youtube.com, m.youtube.com,
    music.youtube.com and youtu.be, with or without `www.` and scheme. Other query parameters and the
    fragment are ignored. Playlist-only URLs and other hosts give None.
    """
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return None
    segments = [s for s in parts.path.split("/") if s]
    candidate: str | None = None
    if host == "youtu.be":
        candidate = segments[0] if segments else None
    elif host in _YOUTUBE_HOSTS:
        if parts.path == "/watch" or parts.path == "/watch/":
            values = parse_qs(parts.query).get("v")
            candidate = values[0] if values else None
        elif len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
            candidate = segments[1]
    if candidate is not None and _VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def workspace_id_for_youtube(video_id: str) -> str:
    """`yt-<video id>`."""
    if not _VIDEO_ID_RE.match(video_id):
        raise ValueError(f"invalid YouTube video id {video_id!r}")
    return validate_workspace_id(f"yt-{video_id}")


def workspace_id_for_bytes(sha256_hex: str) -> str:
    """`sha256-<first 32 hex characters>`."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256_hex):
        raise ValueError("expected a 64-character lowercase SHA-256 hex digest")
    return validate_workspace_id(f"sha256-{sha256_hex[:32]}")


def sha256_file(path: Path, chunk_size: int) -> str:
    """SHA-256 hex digest of a file, read in `chunk_size` pieces."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class HashingWriter:
    """Wraps a binary file object and hashes everything written through it, so a download or upload
    is hashed while streaming to disk and never read twice.

    `chunk_size` is the largest piece hashed or written at once (`sources.hash_chunk_bytes`).
    """

    def __init__(self, fileobj: BinaryIO, chunk_size: int) -> None:
        self._f = fileobj
        self._chunk = chunk_size
        self._digest = hashlib.sha256()
        self.bytes_written = 0

    def write(self, data: bytes) -> int:
        view = memoryview(data)
        for start in range(0, len(view), self._chunk):
            piece = view[start : start + self._chunk]
            self._digest.update(piece)
            self._f.write(piece)
        self.bytes_written += len(view)
        return len(view)

    def flush(self) -> None:
        self._f.flush()

    def hexdigest(self) -> str:
        return self._digest.hexdigest()
