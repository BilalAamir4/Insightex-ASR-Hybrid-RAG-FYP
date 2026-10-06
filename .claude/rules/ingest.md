---
paths:
  - "backend/src/insightex/ingest/**"
  - "backend/src/insightex/media/**"
  - "backend/src/insightex/core/manifest.py"
  - "backend/src/insightex/jobs/ingest_jobs.py"
  - "backend/src/insightex/api/routers/ingest.py"
  - "backend/tests/**/test_ingest*.py"
---
# Ingest (M2 upload, M3 link) — loaded only when touching ingest code

Status: link ingestion is done (6 Oct 2026). Local file upload is still to do and should reuse the same normalisation path.

- One path for every source: download the whole file, then normalise and play it locally. There is no embedded YouTube player and no audio-only path.
- YouTube and public Google Drive go through yt-dlp. gdown was removed. Deno inside the venv is yt-dlp's JS runtime. Direct URLs are fetched directly.
- Output goes to `$INSIGHTEX_DATA/lectures/<lecture_id>/`: `video.mp4` (H.264/AAC), `audio.wav` (16 kHz mono), `thumbnail.jpg` and `manifest.json` (schema v2, with `source` and decision fields). If you change the manifest, bump the schema version.
- Limits are 3 h and 4 GB. The user must confirm they have the rights to the video. Validate with ffprobe and reject unsupported codecs cleanly.
- Known gaps (do not claim these are handled):
  - no storage cleanup or quota
  - the yt-dlp Drive fallback is untested
  - the SSRF guard has a DNS-rebinding gap
  - HEVC decode is tested only on synthetic input
  - the demo-venue network is untested
- Planned (M1): cache workspaces by content hash or YouTube ID plus pipeline version.
