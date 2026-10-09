# ADR-0036: Local-file ingestion and shared media normalisation policy

Status: Accepted
Date decided: 2026-10-09
Date recorded: 2026-10-09
Module: M2

## Context

M2 adds ingestion of a local video file. Link ingestion (M3, ADR-0035) already normalises a downloaded file to `video.mp4`, `audio.wav` and `thumbnail.jpg`, but its rules were thin: it remuxed only H.264/AAC in an MP4 container, forced a constant frame rate on every transcode, checked little after the fact and never looked at where the audio started. Every answer cites a timestamp from the Whisper transcript of `audio.wav`, and the player seeks `video.mp4` to that time (`seekTo(seconds)`). A drift between the two files corrupts every citation silently, so the timeline must be right before anything is built on it.

The M2 brief was written against the pre-M1 layout (`lectures/<lecture_id>/`, manifest v2). That layout was retired in ADR-0035, so the brief's terms map as follows: `lecture_id` is the workspace id (`sha256-<32 hex>`, the id the API already calls `lecture_id`), the "manifest source and decision blocks" are `source.json` (written by the first stage) and `normalise.json` (written by `normalise`), and the "normaliser version" is `NormaliseStage.version`, which feeds the chained stage key (ADR-0034). The workspace `manifest.json` (schema 1) is unchanged.

## Decision

One engine, two entry points. The decisions below are numbered as in the brief.

- **D1. One engine.** `insightex.media.engine.normalise_media(source, out_dir, ...)` performs probe, validate, normalise, extract audio, verify, thumbnail and returns the record saved as `normalise.json`. Pure rules (stream choice, copy-or-transcode, probe validation) are in `insightex.media.policy` and are unit-tested on canned ffprobe JSON. `NormaliseStage` is the only caller and is the second stage of both pipelines: `ingest_link` (`fetch`, `normalise`) and the new `ingest_file` (`fetch`, `normalise`). The `fetch` stage of `ingest_file` adopts a staged copy of the file (hard link, else copy) as `source`, so everything after it is the same code. The HTTP upload in session 2 calls the same `enqueue_file` as the CLI.
- **D2. Copy or transcode per stream, CPU only.** Video is copied only if codec is h264, pix_fmt is yuv420p or yuvj420p, profile is Constrained Baseline, Baseline, Main or High, width and height are even, and the field order is progressive or unknown. Audio is copied only if codec is aac, profile is LC, channels are at most 2 and the sample rate is 44100 or 48000. Otherwise that stream is transcoded with libx264 or the native aac encoder. No NVENC and no GPU lease in any M2 stage. `normalise.json` records which condition failed (`decision.reasons`). The `.mp4` container requirement of the old remux rule is gone: the streams are what matter, and ffmpeg re-wraps them.
- **D3. Transcode parameters** (config under `ingest.transcode`): `-c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -profile:v high`; `yadif` only for interlaced sources, then `scale=w=-2:h='min(1080,trunc(ih/2)*2)'` (downscale only, even sizes); `-force_key_frames expr:gte(t,n_forced*2)`; `-fps_mode vfr` (see below); audio `-c:a aac -b:a 160k -ar 48000`, `-ac 2` only above two channels, `-af aresample=async=1:first_pts=0`. Always: an explicit `-map` of the two chosen streams, `-sn -dn -map_chapters -1`, `-movflags +faststart`, written to `video.mp4.part` and renamed.
  - **Departure from the brief: no `-avoid_negative_ts make_zero`.** With it, a transcode that uses B-frames moves the decoder delay into presentation time. Fixture 16 (HEVC and Opus in MKV, audio delayed 0.7 s) gave a flash at 5.080 s and a beep at 5.022 s, a 57.6 ms offset, against 1.1 ms without the flag (flash 5.000 s, beep 5.001 s). Without the flag, fixtures 14 and 15 (a 10 s MPEG-TS offset) and every accepted fixture still pass the post-verify rules. The flag is not used anywhere; a unit test and fixture 16 fail if it returns.
  - **`-fps_mode vfr`.** The MP4 muxer would otherwise default to constant frame rate and duplicate or drop frames. The old forced `-r` constant rate is gone; source frame timing is kept.
  - The 1080-line cap applies to transcoded video only (D7): copied video keeps its source resolution.
- **D4. Timeline alignment.** `audio.wav` is derived from the finished `video.mp4`, never from the source: `ffmpeg -i video.mp4 -map 0:a:0 -af aresample=async=1:first_pts=0 -ac 1 -ar 16000 -c:a pcm_s16le`. The padding filter makes `audio.wav` t=0 equal player t=0 even when the audio stream starts late. No loudness normalisation or other audio processing.
- **D5. Validation: anything ffmpeg can decode, plus structural rules,** with a closed set of error codes (table below). Stream choice: video is the first stream that is not cover art (`attached_pic`), preferring `default`; audio is the `default` stream, else the first.
- **D6. Artifact names** stay `video.mp4`, `audio.wav`, `thumbnail.jpg` (and the manifest files). The build plan's `proxy.mp4` and `audio16k.wav` names were never used in code and are superseded; `docs/BUILD_ORDER.md` no longer uses "proxy".
- **D7. Copied streams keep their source resolution;** only transcoded video is capped at `ingest.transcode.max_height` (1080).
- **D8. Identity and dedupe.** The staged copy gets a full SHA-256 computed while copying (8 MiB chunks, `ingest.file.copy_chunk_bytes`). The workspace id is `sha256-<first 32 hex>`, the same scheme link ingestion already uses for non-YouTube sources, so a file and a direct link with the same bytes share a workspace. Before enqueueing: a queued or running `ingest_file` job for that workspace is returned; a workspace whose `normalise.json` carries the current `normaliser_version` is returned without a job (`job_id` is null, `deduplicated` is true); an older version is re-normalised into the same workspace (the new version changes the `normalise` stage key). A duplicate's staged copy is deleted.
- **D9. Originals.** The staged copy is deleted as soon as the `fetch` stage has published its output. After a successful `normalise`, the uploaded `source` is deleted unless `ingest.file.keep_original` is true (default false). On any rejection the staged copy is deleted at once and the job's workspace and cache row are removed (a workspace that already holds a finished `normalise` is left alone); the job record keeps the code and message. The user's own file is never moved, modified or locked.
  - **The flag is scoped to file ingest, and links are unchanged.** A link's downloaded `source` is kept (ADR-0035): it cannot be re-obtained cheaply (network, availability, demo risk), and deleting it would make `fetch` uncached. An uploaded `source` is deleted because the user still holds the original. Storage clean-up or a quota for kept link sources remains an open item; this ADR does not solve it.
- **D10. Normaliser version bumped to "2"** (`insightex.media.engine.NORMALISER_VERSION`, used as `NormaliseStage.version`), which invalidates every earlier cached normalisation through the chained stage keys.

Supporting rules:

- **Staging.** The CLI copies the file into `<ingest.file.staging_dir>/<uuid>.tmp` while hashing, fsyncs, renames it to `<uuid>.part` and fsyncs the directory. The directory defaults to `<paths.data_dir>/staging`, on the same filesystem as the workspaces. Reading from `/mnt/...` works because the file is only read. At worker start, staging files older than `ingest.file.staging_max_age_h` (24 h) that no queued or running job refers to are deleted. A user-supplied file name is display text (sanitised, 200 characters at most) and never reaches a path.
- **Order of checks.** Free disk space (at least `disk_free_factor` x size plus `disk_free_reserve_bytes`) is checked before the copy and raises `INSUFFICIENT_DISK` to the caller, so no job exists. The size checks (`EMPTY_FILE`, `TOO_LARGE`) and everything after them run in the job, so a rejection reaches the user through the job record.
- **Post-verify.** Both outputs are re-probed. `video.mp4` must hold exactly one h264 yuv420p/yuvj420p stream and one aac stream with `moov` before `mdat`; its duration must match the source within `max(2 s, 1%)`; its minimum stream start must be within 0.1 s of zero; and `audio.wav` must be pcm_s16le 16 kHz mono with (wav duration minus the mp4 audio duration) equal to the mp4 audio start time within 0.1 s. Tolerances are config (`ingest.verify.*`).
- **Warnings** (recorded in `normalise.json`, never fatal): `AUDIO_NEAR_SILENT`, `MULTIPLE_AUDIO_STREAMS`, `VFR_SOURCE`, `ROTATED`, `AV_DURATION_MISMATCH`, `START_OFFSET_CORRECTED`.
- **Records.** `source.json` carries `kind` (`link` or `upload`), `via` (`cli`; `http` in session 2; null for links), `original_filename`, `size_bytes`, `sha256`, `received_at`. `normalise.json` (`schema: 2`) carries that source block, the probe summary, the decision and reasons, the normaliser and ffmpeg versions, per-step timings, warnings and the post-verify measurements. This is additive: old readers use `duration_s`, which is still there, and the workspace `manifest.json` stays at schema 1.
- **Runner changes.** `Stage.after_stage` (idempotent hook after a stage succeeds or is found cached) and a per-pipeline `on_failure` hook were added to the runner so clean-up that is only safe after publishing lives with the pipeline, not in the generic runner. `_publish` now replaces a same-key stage directory that is missing a declared output (found by the re-normalise test): once a hook deletes an output after publishing, such as an uploaded original, a rerun with the same key would otherwise keep the old, incomplete directory and discard the fresh output, so the next stage found nothing to read. Guarded by `test_publish_replaces_a_same_key_directory_whose_output_was_deleted`.

### Error codes

One enum (`ingest.errors.ErrorCode`) in the existing unprefixed style. No code already in use was renamed (old job rows store them). The engine raises `IngestRejected` (a subclass of `IngestError`) for an unusable file, with `details` (for example the last 20 lines of ffmpeg's stderr) kept in the job's stage error and the worker log, never in the user message. The brief's names map as follows: `INGEST_NOT_MEDIA` is `NOT_A_VIDEO`, `INGEST_NO_VIDEO` is the new `NO_VIDEO_STREAM`, `INGEST_NO_AUDIO` is `NO_AUDIO_STREAM`, `INGEST_DECODE_FAILED` is `TRANSCODE_FAILED`, `INGEST_RIGHTS_NOT_CONFIRMED` is `RIGHTS_NOT_CONFIRMED`.

| Code | Meaning | User message | Raised by |
|---|---|---|---|
| `EMPTY_FILE` | 0 bytes | This file is empty. | `normalise` (rule 1) |
| `TOO_LARGE` | over 4 GiB (`ingest.url.max_download_bytes`) | This video file is too large. | `fetch` (links), `normalise` (rule 1) |
| `INSUFFICIENT_DISK` | free space below factor x size + reserve | There isn't enough free disk space to process this video. | `enqueue_file` (before the copy), `normalise` (rule 2) |
| `NOT_A_VIDEO` | ffprobe fails, times out (60 s) or finds no streams. Existing code: before M2 it also meant "no video track", which now has its own code | This doesn't look like a video file we can read. | `fetch` (links, wrong content type), `normalise` (rule 3) |
| `NO_VIDEO_STREAM` | media, but no usable video stream (audio only, cover art only) | This file has no video track. Only video files can be added. | `normalise` (rule 4) |
| `NO_AUDIO_STREAM` | no audio stream | This video has no audio track, so it can't be transcribed. | `normalise` (rule 4) |
| `UNSUPPORTED_CODEC` | no ffmpeg decoder for a chosen stream | This video uses a format we can't read. | `normalise` (rule 5) |
| `DURATION_UNKNOWN` | duration missing, zero or not a number | We couldn't tell how long this video is, so it can't be added. | `normalise` (rule 6) |
| `TOO_SHORT` | under `ingest.min_duration_s` (10 s) | This video is too short to add. | `normalise` (rule 6) |
| `TOO_LONG` | over 3 h (`ingest.url.max_duration_s`) | This video is longer than the 3 hours limit. | `fetch` (links), `normalise` (rule 6) |
| `TRANSCODE_FAILED` | ffmpeg failed or timed out (`max(300 s, 3 x duration)`), or an output-format check failed | The video file couldn't be processed. It may be damaged. | `normalise` (rules 7, 8a, 8e, thumbnail) |
| `TRUNCATED` | `video.mp4` much shorter than the source | This video looks cut off or damaged: the processed copy is much shorter than the original. | `normalise` (rule 8b) |
| `SYNC_CHECK_FAILED` | stream start or audio padding check failed | We couldn't line up the sound with the picture in this video, so it can't be added. | `normalise` (rules 8c, 8d) |
| `RIGHTS_NOT_CONFIRMED` | rights not confirmed (existing) | Please confirm you have the right to use this video before adding it. | CLI, API |
| `LENGTH_REQUIRED`, `UPLOAD_BUSY`, `UPLOAD_INTERRUPTED` | reserved for the HTTP upload (session 2); nothing raises them yet | (messages defined) | none yet |

The other existing link codes (`UNSUPPORTED_URL`, `PLAYLIST_NOT_SUPPORTED`, `LIVE_NOT_SUPPORTED`, `PRIVATE_OR_LOGIN_REQUIRED`, `AGE_RESTRICTED`, `GEO_BLOCKED`, `DRIVE_NOT_SHARED`, `DRIVE_QUOTA_EXCEEDED`, `BLOCKED_ADDRESS`, `NETWORK_ERROR`, `DOWNLOAD_FAILED`) are fetch-time codes and are unchanged.

### A/V alignment guarantee and how it is tested

Guarantee: for an accepted file, the time of any event in `audio.wav` equals the time at which the player shows the matching moment of `video.mp4`, within one video frame. It holds because `audio.wav` comes from `video.mp4` with a padding filter, `video.mp4` stream start times are within 0.1 s of zero, and the padding equals the audio stream's start time (rules 8c and 8d, checked on every file).

Test (`backend/tests/integration/test_media_engine.py::test_flash_and_beep_coincide`): a black video with a white full-frame flash from 5.0 s to 5.2 s and a 1 kHz beep over the same span in the container timeline, in three containers. The flash time is the first frame in `video.mp4` whose `signalstats` YAVG exceeds 128; the beep time is the first `audio.wav` sample above 25% full scale (stdlib `wave`). The bar is one frame duration of the fixture (40 ms at 25 fps), computed from its `r_frame_rate`. Measured offsets (beep minus flash):

| Fixture | What it exercises | Flash | Beep | Offset |
|---|---|---|---|---|
| 14 `sync_audio_delayed_mp4` | audio stream starts 1.5 s late, both copied | 5.000 s | 4.999 s | -0.6 ms |
| 15 `sync_ts_offset_mpegts` | whole file starts at 10 s, both copied | 5.021 s | 5.021 s | +0.4 ms |
| 16 `sync_hevc_opus_delayed_mkv` | HEVC and Opus, audio 0.7 s late, both transcoded | 5.000 s | 5.001 s | +1.1 ms |

## Alternatives considered

- **D1.** Separate normalisers for links and files: two places to get timestamps wrong. Rejected.
- **D2.** Always transcode: simplest and safest, but slower for the common already-compatible lecture (not measured here) and a needless generation loss. Always remux (the old rule for MP4 only): breaks on HE-AAC, 5.1, 10-bit and odd sizes. Per-stream copy keeps the fast path and falls back per stream.
- **D3.** `-avoid_negative_ts make_zero` (the brief): measured 57.6 ms skew on a B-frame transcode (above). Forced constant frame rate (the old behaviour): duplicates or drops frames and moves timestamps. NVENC: breaks "no GPU in M2" and the GPU lease contract.
- **D4.** Extract audio from the source: one pass fewer, but the two files then disagree whenever the source's audio starts late or the transcode shifts anything. Loudness normalisation: changes what Whisper hears for no measured gain.
- **D5.** A fixed allow-list of extensions or codecs: rejects files ffmpeg handles fine, and trusts file names. Using ffmpeg's own decoder list plus structural checks lets a new codec work without code.
- **D8.** Lecture id from the file name or a UUID: the same bytes could be ingested twice. A content hash costs one pass over the copy, which is already being read.
- **D9.** Delete link sources too (the brief asked for this): makes `fetch` uncached, so every repeated link downloads again; rejected by the owner (ADR-0035 stands). Keep uploads: doubles disk use for no gain.
- **Early size rejection at enqueue.** Cheaper for a 5 GB file (nothing copied), but then no job record holds the code. The disk check stays early because it must precede the copy; session 2's upload can also reject by `Content-Length` before reading the body.

## Consequences

- Local files and links share every media rule. A link now also gets `TOO_SHORT`, the stream-based copy rule, and the post-verify checks (behaviour changes are listed in the M2 session 1 report).
- Link `source` files are still kept (ADR-0035); disk is bounded by `cache.max_bytes` eviction only.
- Uploaded `source` files are deleted after success, so re-normalising an older lecture needs the user to ingest the file again (the CLI does this and reuses the workspace id).
- A staged file belonging to a job that waits more than 24 h is protected from the sweep; one whose job was cancelled or failed internally is removed after 24 h.
- `ingest.transcode.preset` default changed from `medium` to `veryfast`.

## Evidence

`backend/tests/unit/test_media_policy.py` (decision and validation order on canned ffprobe JSON, argument construction); `backend/tests/integration/test_media_engine.py` (synthetic corpus of 31 cases, real ffmpeg, in-process jobs); `backend/tests/integration/test_media_worker.py` (kill -9 resume, `--wait` exit codes). Run the media suite alone with `pytest -m media`. The make_zero measurements above were taken on this machine (ffmpeg 6.1.1, libx264) and are in the test docstring as a regression note.

## Gate / revisit when

Revisit when the HTTP upload (session 2) finds the staging or dedupe flow insufficient; when kept link sources need a quota or clean-up (open item); when the Day 4 lecture does not normalise or a real lecture trips a rule that the synthetic corpus did not; or when a different encoder or ffmpeg version changes the B-frame behaviour measured here.
