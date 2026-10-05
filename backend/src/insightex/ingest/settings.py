"""Ingestion limits, read from config/default.yaml (paths.lectures, ingest.url.*)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from insightex.core.config import load_config, require_path


@dataclass(frozen=True)
class IngestSettings:
    lectures_dir: Path
    max_duration_s: int = 10800
    max_download_bytes: int = 4 * 1024**3
    keep_source: bool = False
    max_video_height: int = 1080
    deno_path: str | None = None

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> IngestSettings:
        cfg = load_config() if cfg is None else cfg
        url = (cfg.get("ingest") or {}).get("url") or {}
        lectures = require_path((cfg.get("paths") or {}).get("lectures"), "paths.lectures")
        defaults = cls(lectures_dir=lectures)
        return cls(
            lectures_dir=lectures,
            max_duration_s=int(url.get("max_duration_s", defaults.max_duration_s)),
            max_download_bytes=int(url.get("max_download_bytes", defaults.max_download_bytes)),
            keep_source=bool(url.get("keep_source", defaults.keep_source)),
            max_video_height=int(url.get("max_video_height", defaults.max_video_height)),
            deno_path=url.get("deno_path") or None,
        )
