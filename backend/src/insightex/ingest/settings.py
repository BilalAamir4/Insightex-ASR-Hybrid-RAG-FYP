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
    ffprobe_timeout_s: float = 60
    max_url_length: int = 2048
    preset: str = "veryfast"
    crf: int = 23
    thumb_max_width: int = 1280
    thumb_quality: int = 3
    thumb_max_bytes: int = 10 * 1024 * 1024
    transcode_max_height: int = 1080
    audio_bitrate_kbps: int = 160
    keyframe_interval_s: float = 2.0
    min_duration_s: float = 10.0
    silence_warn_dbfs: float = -50.0
    disk_free_factor: float = 2.5
    disk_free_reserve_bytes: int = 1024**3
    ffmpeg_timeout_factor: float = 3.0
    ffmpeg_timeout_min_s: float = 300.0
    duration_tolerance_s: float = 2.0
    duration_tolerance_frac: float = 0.01
    sync_tolerance_s: float = 0.1
    av_mismatch_warn_s: float = 1.0

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
            transcode_max_height=i.transcode.max_height,
            audio_bitrate_kbps=i.transcode.audio_bitrate_kbps,
            keyframe_interval_s=i.transcode.keyframe_interval_s,
            min_duration_s=i.min_duration_s,
            silence_warn_dbfs=i.silence_warn_dbfs,
            disk_free_factor=i.disk_free_factor,
            disk_free_reserve_bytes=i.disk_free_reserve_bytes,
            ffmpeg_timeout_factor=i.ffmpeg_timeout_factor,
            ffmpeg_timeout_min_s=i.ffmpeg_timeout_min_s,
            duration_tolerance_s=i.verify.duration_tolerance_s,
            duration_tolerance_frac=i.verify.duration_tolerance_frac,
            sync_tolerance_s=i.verify.sync_tolerance_s,
            av_mismatch_warn_s=i.verify.av_mismatch_warn_s,
        )

    @classmethod
    def current(cls) -> IngestSettings:
        """From the cached process settings. Used where a caller passed no settings (tests, one-off scripts)."""
        return cls.from_settings(get_settings())
