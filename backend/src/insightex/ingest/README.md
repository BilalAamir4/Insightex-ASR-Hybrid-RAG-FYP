# insightex.ingest

**Purpose:** Video ingestion from a pasted URL (YouTube, Google Drive "anyone with the link", direct video URLs).
Every source is fully downloaded, normalized to H.264/AAC mp4 and stored locally; there is no embedded player
and no audio-only download.

**Model used:** none (yt-dlp, httpx, FFmpeg on CPU)

**Feature numbers:** not assigned

**Status:** link ingestion runs as the `ingest_link` pipeline on the stage runner (ADR-0035). Local upload (M2) not yet.

## Modules

- `urls.py`: URL classification, normalization, canonical ids (`yt:<id>`, `gdrive:<id>`, `url:<sha256[:16]>`).
- `netguard.py`: SSRF guard for direct URLs (public addresses only, re-checked on every redirect).
- `sources/`: per-source probe + download (`youtube.py`, `gdrive.py`, `direct.py`, shared `ytdlp.py`).
- `probe.py`: `probe(url)` and the per-source adapter table.
- `pipeline.py`: the `fetch` and `normalise` stages and the `ingest_link` registration.
- `link_jobs.py`: `enqueue_link(...)`: validation, workspace id, de-duplication.
- `errors.py`: `IngestError(code, message)` with the fixed code set.
- `settings.py`: `IngestSettings`, built from the typed settings (`ingest.*`, `paths.data_dir`).
- `cli.py`: `insightex probe <url>` / `insightex ingest <url> --confirm-rights` (enqueues; a worker runs it).

## Output contract

`$INSIGHTEX_DATA/workspaces/<workspace_id>/stages/fetch/<key>/`: `source` (the downloaded file), `source.json`, optionally `thumbnail.src`.
`.../stages/normalise/<key>/`: `video.mp4` (H.264 <=1080p + AAC, faststart), `audio.wav` (16 kHz mono pcm_s16le, extracted
from video.mp4 so ASR timestamps match the player), `thumbnail.jpg`, `normalise.json`. Find them with
`Workspaces.stage_output_dir(id, "normalise")`. The old `lectures/<lecture_id>/` layout is retired.

## Known limits

- DNS rebinding: the address is checked, then httpx resolves again to connect (not pinned; pinning breaks TLS SNI).
- Direct URLs: duration is unknown at probe time; the limit is enforced by ffprobe after download.
- YouTube needs a JavaScript runtime: the venv-local `deno` wheel, passed to yt-dlp via `js_runtimes`.
