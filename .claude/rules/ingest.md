---
paths:
  - "backend/src/insightex/ingest/**"
  - "backend/src/insightex/media/**"
  - "backend/src/insightex/jobs/rebind.py"
  - "backend/src/insightex/api/routers/ingest.py"
  - "backend/tests/**/test_ingest*.py"
---
# Ingest (M2 upload, M3 link) — loaded only when touching ingest code

Status: link ingestion runs on the stage runner (M1 session 3, ADR-0035). Local file upload (M2) is still to do and should reuse the `normalise` stage.

- One path for every source: download the whole file, then normalise and play it locally. There is no embedded YouTube player and no audio-only path.
- YouTube and public Google Drive go through yt-dlp. gdown was removed. Deno inside the venv is yt-dlp's JS runtime. Direct URLs are fetched directly with httpx behind the SSRF guard.
- Flow: `POST /api/ingest/link` (`{url, rights_confirmed}`; 400 unless the rights flag is `true` or the link is unsupported) enqueues an `ingest_link` job (`ingest/link_jobs.py`); the worker runs two CPU stages in `ingest/pipeline.py`:
  - `fetch`: download into staging; outputs `source` (the original file), `source.json` (url, title, duration, downloader version, sha256), optional `thumbnail.src`.
  - `normalise`: `video.mp4` (H.264/AAC), `audio.wav` (16 kHz mono), `thumbnail.jpg`, `normalise.json`; ffprobe validates both media files before the stage succeeds; progress comes from `ffmpeg -progress`.
- Workspace id: `yt-<id>` for YouTube (known at enqueue). Any other link starts as `pending-<job id>` and is rebound to `sha256-<32 hex>` after `fetch` (`jobs/rebind.py`). The first stage's key chains from `yt-<id>` or the normalised URL, never from the provisional id (`chain_root`).
- Output goes to `$INSIGHTEX_DATA/workspaces/<workspace_id>/stages/<stage>/<key>/`; find files with `Workspaces.stage_output_dir(id, "normalise")`, not by path. The old `lectures/<lecture_id>/` layout and its v2 manifest are retired; old lectures must be re-ingested.
- The fetch output (`source`) is a declared output and is kept: deleting it would make `fetch` uncached. Disk is bounded by `cache.max_bytes` and eviction.
- Tests that need a local HTTP server use the `allow_loopback` / `video_server` fixtures. The SSRF guard has no flag or environment variable to allow loopback in production; do not add one.
- Limits are 3 h and 4 GB. The user must confirm they have the rights to the video. Reject unsupported codecs cleanly.
- Known gaps (do not claim these are handled):
  - the yt-dlp Drive fallback is untested
  - the SSRF guard has a DNS-rebinding gap
  - HEVC decode is tested only on synthetic input
  - the demo-venue network is untested
  - a different URL serving identical bytes merges into the existing `sha256-` workspace and re-runs `normalise`
