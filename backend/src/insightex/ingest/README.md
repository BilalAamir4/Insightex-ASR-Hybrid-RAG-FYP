# insightex.ingest

**Purpose:** Video ingestion from a pasted URL (YouTube, Google Drive "anyone with the link", direct video URLs).
Every source is fully downloaded, normalized to H.264/AAC mp4 and stored locally; there is no embedded player
and no audio-only download.

**Model used:** none (yt-dlp, gdown, httpx, FFmpeg on CPU)

**Feature numbers:** not assigned

**Status:** URL ingestion engine + test CLI implemented. Upload ingestion, API endpoints and UI not yet.

## Modules

- `urls.py`: URL classification, normalization, canonical ids (`yt:<id>`, `gdrive:<id>`, `url:<sha256[:16]>`).
- `netguard.py`: SSRF guard for direct URLs (public addresses only, re-checked on every redirect).
- `sources/`: per-source probe + download (`youtube.py`, `gdrive.py`, `direct.py`, shared `ytdlp.py`).
- `engine.py`: `probe(url)` and `ingest(url, rights_confirmed, progress_cb)`; dedup, locking, atomic moves.
- `errors.py`: `IngestError(code, message)` with the fixed code set.
- `settings.py`: limits from `config/default.yaml` (`paths.lectures`, `ingest.url.*`).
- `cli.py`: `python -m insightex.ingest.cli probe <url>` / `ingest <url> --confirm-rights`.

## Output contract

`$INSIGHTEX_DATA/lectures/<lecture_id>/`: `video.mp4` (H.264 <=1080p + AAC, faststart), `audio.wav`
(16 kHz mono pcm_s16le, extracted from video.mp4 so ASR timestamps match the player), `thumbnail.jpg`,
`manifest.json` (see `insightex.core.manifest`), and `source.<ext>` only when `keep_source` is true.
Not connected to ASR or any later stage.

## Known limits

- DNS rebinding: the address is checked, then httpx resolves again to connect (not pinned; pinning breaks TLS SNI).
- Direct URLs: duration is unknown at probe time; the limit is enforced by ffprobe after download.
- YouTube needs a JavaScript runtime: the venv-local `deno` wheel, passed to yt-dlp via `js_runtimes`.
