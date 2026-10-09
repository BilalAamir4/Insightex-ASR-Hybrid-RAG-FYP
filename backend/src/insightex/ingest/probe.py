"""Link probing and the per-source adapter table: metadata without downloading media.

The `fetch` and `normalise` pipeline stages (ingest/pipeline.py) do the downloading and conversion.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any

from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources import direct, gdrive, youtube
from insightex.ingest.urls import parse_url
from insightex.jobs.workspace import Workspaces
from insightex.sources.identity import workspace_id_for_youtube

log = logging.getLogger(__name__)

SOURCES: dict[str, Any] = {
    "youtube": SimpleNamespace(probe=youtube.probe, download=youtube.download),
    "gdrive": SimpleNamespace(probe=gdrive.probe, download=gdrive.download),
    "direct": SimpleNamespace(probe=direct.probe, download=direct.download),
}


@dataclass
class ProbeResult:
    canonical_id: str
    workspace_id: str | None  # known before download only for YouTube
    source_type: str
    normalized_url: str
    title: str | None
    uploader: str | None
    duration_s: float | None
    thumbnail_url: str | None
    exists_locally: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def too_long_message(limit_s: int) -> str:
    hours = limit_s / 3600
    limit = f"{hours:g} hours" if hours >= 1 else f"{limit_s // 60} minutes"
    return f"This video is longer than the {limit} limit."


def check_duration(duration_s: float | None, settings: IngestSettings) -> None:
    if duration_s is not None and duration_s > settings.max_duration_s:
        raise IngestError(ErrorCode.TOO_LONG, too_long_message(settings.max_duration_s))


def probe(url: str, settings: IngestSettings, workspaces: Workspaces | None = None) -> ProbeResult:
    """Metadata without downloading media. Raises IngestError (TOO_LONG when the duration is known).

    `exists_locally` is true only for a YouTube link whose workspace has a completed `normalise` stage.
    """
    parsed = parse_url(url, settings.max_url_length)
    workspace_id = workspace_id_for_youtube(parsed.media_id) if parsed.source_type == "youtube" else None
    if workspaces and workspace_id and workspaces.stage_output_dir(workspace_id, "normalise"):
        fetched = workspaces.stage_output_dir(workspace_id, "fetch")
        info = _read_json(fetched / "source.json") if fetched else {}
        return ProbeResult(
            canonical_id=parsed.canonical_id, workspace_id=workspace_id, source_type=parsed.source_type,
            normalized_url=parsed.normalized_url, title=info.get("title"), uploader=info.get("uploader"),
            duration_s=info.get("duration_s"), thumbnail_url=None, exists_locally=True,
        )
    exists = False
    meta = SOURCES[parsed.source_type].probe(parsed, settings)
    check_duration(meta.duration_s, settings)
    return ProbeResult(
        canonical_id=parsed.canonical_id, workspace_id=workspace_id, source_type=parsed.source_type,
        normalized_url=parsed.normalized_url, title=meta.title, uploader=meta.uploader,
        duration_s=meta.duration_s, thumbnail_url=meta.thumbnail_url, exists_locally=exists,
    )
