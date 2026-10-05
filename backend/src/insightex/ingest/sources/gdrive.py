"""Google Drive adapter (yt-dlp).

yt-dlp requests Drive's "source" format (the original upload) with confirm=t, which skips the large-file
virus-scan page. If Drive stops honouring that, yt-dlp falls back to parsing the page's download form;
that fallback has not been exercised by a test against the real service.
"""

from __future__ import annotations

from pathlib import Path

from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources import ytdlp
from insightex.ingest.sources.base import BytesCb, SourceMeta
from insightex.ingest.urls import ParsedUrl

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
    return ytdlp.download(
        parsed.normalized_url, dest_dir, settings, "gdrive", DRIVE_FORMAT, on_bytes, merge_mp4=False
    )
