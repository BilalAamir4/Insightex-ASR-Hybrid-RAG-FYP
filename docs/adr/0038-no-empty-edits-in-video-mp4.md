# ADR-0038: video.mp4 must not rely on an empty edit to stay in sync

Status: Accepted
Date decided: 2026-10-09
Date recorded: 2026-10-09
Module: M2

## Context

ADR-0036 copies a stream when it is already H.264 or AAC. A source whose audio (or video) stream starts late is stored in MP4 as an **empty edit** (an `elst` entry with `media_time` -1) on that track, and `-c copy` carried it into `video.mp4`. ffmpeg honours it, so `audio.wav` (derived from `video.mp4`) was in sync. A player that ignores empty edits plays the track from its first sample and is shifted by the whole offset.

Bilal saw this in a Windows browser: on the delayed-audio fixture the flash and the beep were visibly apart, in the source and in `video.mp4` alike. Measurement (flash 5.0 s, beep designed for 5.0 s; offset = beep minus flash; 9 Oct 2026, one fixture, ffmpeg decode):

| Where | Offset before the fix | Offset after the fix |
|---|---|---|
| source, edit lists honoured | -0.6 ms | n/a (source unchanged) |
| `video.mp4`, edit lists honoured | -0.6 ms | -0.6 ms |
| `video.mp4`, `-ignore_editlist 1` | **-1478.6 ms** | +20.7 ms |
| `audio.wav` | -0.6 ms | -0.6 ms |

Before the fix `video.mp4` had an audio track with an empty edit of 1478 ms and a stream `start_time` of 1.478 s.

## Decision

- **Late audio.** If the chosen audio stream starts more than one video frame after the video stream, the audio is transcoded (AAC) with `aresample=async=1:first_pts=0`. `video.mp4`'s audio then starts at 0 with leading silence and needs no empty edit.
- **Late video.** If the video stream starts more than one frame after the audio, the video is transcoded and its start is padded by holding the first frame: `setpts=PTS-STARTPTS,tpad=start_duration=<offset>:start_mode=clone`. The video track then starts at 0.
- **One frame** is 1 / the video's average frame rate (25 fps if unknown), capped at `ingest.verify.sync_tolerance_s`. The decision is in `media/policy.py` (`decide`, `Decision.video_pad_s`). The reasons are recorded in `normalise.json` as before.
- **Post-verify** (`verify_outputs`): both tracks of `video.mp4` must have a stream `start_time` within one frame of 0, and neither may have an empty edit longer than one frame. A failure is `SYNC_CHECK_FAILED`. The checker reads the edit lists itself (`mp4_edit_lists`).
- **Departure from the literal brief.** The brief said no empty edit at all. Common sources carry a few milliseconds of one (Opus pre-skip -7 ms, an MPEG-TS stream offset 21 ms, a 40 ms AV1 delay), and removing those would mean re-encoding the video of almost every MKV. The rule is therefore "no empty edit longer than one frame", the same threshold that triggers the re-encode: a player that ignores a shorter one is within the sync bar. Revisit if that bar is judged too loose.
- `NORMALISER_VERSION` is "3", so existing lectures re-normalise on a re-upload of the same bytes.
- **Link ingestion is covered.** `ingest_link` and `ingest_file` both call `normalise_media`; there is no second path.

## Alternatives considered

- **Keep the copy and document the browser limitation.** Rejected: every citation seeks `video.mp4`, and a 1.5 s shift is visible.
- **Rewrite only the container timestamps (`-itsoffset`, `-copyts`).** Rejected for audio: without a sample-accurate pad the track still starts late and needs an edit; the re-encode with leading silence is exact. Rejected for video: padding needs a decoded frame to hold.
- **Always transcode both streams.** Rejected: slow and lossy for the great majority of files that need none of it.

## Consequences

- A source with a late audio stream now costs an AAC re-encode (seconds); a late video stream costs a full video transcode.
- Measured on the fixtures after the change (edit lists ignored, offset beep minus flash): control +21.4 ms, delayed audio +20.7 ms, MPEG-TS offset +21.4 ms (all the 1024-sample AAC priming edit, under one 40 ms frame).
- **Open: the B-frame edit.** Video that goes through libx264 (every transcode, including a late-video fix) carries a **non-empty** edit of 1024 units at 12800/s = 80 ms (2 B-frame delays). A player that ignores edit lists shows such video about 2 frames late: delayed video -58.6 ms, HEVC+Opus fixture 16 (`sync_hevc_opus_delayed_mkv`) -57.6 ms, HEVC+Opus without offsets -51.6 ms (limit 40 ms). Players that honour non-empty edits (needed for AAC priming in any case) are unaffected. This is not fixed here; it was reported for a decision. The three affected cases are `xfail(strict=True)` in `test_flash_and_beep_coincide_when_edit_lists_are_ignored`.

## Evidence

`backend/tests/integration/test_media_engine.py` (`test_flash_and_beep_coincide`, `..._when_edit_lists_are_ignored`, `test_no_track_of_any_sync_clip_has_a_long_empty_edit`, `test_post_verify_rejects_...`), `backend/tests/unit/test_media_policy.py`, `tools/m2_verify` check 9, and `docs/evidence/m2/`. The in-browser result is step 11 of `docs/evidence/m2/BROWSER_CHECKLIST.md`, filled in by hand.

## Gate / revisit when

Revisit when the browser checklist is run (does a browser honour the B-frame edit?), or if the one-frame bar for sub-frame empty edits proves too loose.
