"""Ingestion settings passed to the engine, built from the typed Settings (ingest.*, paths.data_dir).

The field defaults mirror config/default.yaml so tests can build an instance directly;
tests/unit/test_config.py fails if they drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from insightex.core.config import Settings, get_settings


@dataclass(frozen=True)
class IngestSettings:
    max_duration_s: int = 10800
    max_download_bytes: int = 4 * 1024**3
    max_video_height: int = 1080
    deno_path: str | None = None
    socket_timeout_s: float = 30
    connect_timeout_s: float = 15
    read_timeout_s: float = 60
    ffprobe_timeout_s: float = 120
    max_url_length: int = 2048
    preset: str = "medium"
    crf: int = 23
    thumb_max_width: int = 1280
    thumb_quality: int = 3
    thumb_max_bytes: int = 10 * 1024 * 1024

    @classmethod
    def from_settings(cls, s: Settings) -> IngestSettings:
        i, u = s.ingest, s.ingest.url
        return cls(
            max_duration_s=u.max_duration_s,
            max_download_bytes=u.max_download_bytes,
            max_video_height=u.max_video_height,
            deno_path=u.deno_path or None,
            socket_timeout_s=u.socket_timeout_s,
            connect_timeout_s=u.connect_timeout_s,
            read_timeout_s=u.read_timeout_s,
            ffprobe_timeout_s=i.ffprobe_timeout_s,
            max_url_length=i.max_url_length,
            preset=i.transcode.preset,
            crf=i.transcode.crf,
            thumb_max_width=i.thumbnail.max_width,
            thumb_quality=i.thumbnail.quality,
            thumb_max_bytes=i.thumbnail.max_bytes,
        )

    @classmethod
    def current(cls) -> IngestSettings:
        """From the cached process settings. Used where a caller passed no settings (tests, one-off scripts)."""
        return cls.from_settings(get_settings())
