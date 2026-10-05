# insightex.ingest.sources

**Purpose:** Per-source ingestion adapters. Each exposes `probe(parsed, settings) -> SourceMeta` and
`download(parsed, dest_dir, settings, meta, on_bytes) -> Path`.

- `youtube.py`: yt-dlp; H.264 <=1080p + AAC merged to mp4, fallback best <=1080p. Rejects live/upcoming,
  private/members-only, age-restricted.
- `gdrive.py`: yt-dlp (metadata and download of the original "source" file; sends confirm=t, so the virus-scan page is skipped).
- `direct.py`: httpx streaming behind `netguard`, size cap on Content-Length and on bytes received.
- `ytdlp.py`: shared yt-dlp options (no cookies, no login), download with byte cap, error mapping.

**Model used:** none

**Status:** implemented (URL sources). Upload adapter not yet.
