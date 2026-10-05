"""Types shared by the source adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# on_bytes(received_bytes, expected_total_or_None)
BytesCb = Callable[[int, int | None], None]


@dataclass
class SourceMeta:
    title: str | None = None
    uploader: str | None = None
    duration_s: float | None = None
    thumbnail_url: str | None = None
    # Expected download size when the source reports it (Content-Length, yt-dlp filesize).
    size_bytes: int | None = None
    # Suggested extension for the downloaded source file.
    ext: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
