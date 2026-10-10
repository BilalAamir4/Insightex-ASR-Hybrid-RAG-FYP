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

**Invariant.** `video.mp4` must play with at most one video frame of audio/video skew even in a player that ignores ALL edit lists, empty and non-empty. The skew a player would see is computed from the `elst` boxes (`ignored_skew_s`): each track is shifted by its leading empty edits minus its first non-empty `media_time`, and the skew is the difference between the two tracks. The bound is one frame (1 / the average frame rate, capped at `ingest.verify.sync_tolerance_s`) but never less than the AAC priming of the track (1024 samples, 21 to 23 ms), which every AAC track carries as an edit and cannot be removed. At 60 fps this makes the bound 21 to 23 ms rather than 16.7 ms.

- **Late audio.** If the chosen audio stream starts more than one frame after the video, the audio is transcoded (AAC) with `aresample=async=1:first_pts=0`, so it starts at 0 with leading silence and needs no empty edit.
- **Late video.** If the video starts more than one frame after the audio, the video is transcoded and padded by holding its first frame: `setpts=PTS-STARTPTS,tpad=start_duration=<offset>:start_mode=clone`.
- **Transcode path: no B-frames.** libx264 runs with `-x264-params bframes=0`. Output then has no B-frame delay, so the video track carries no edit. Cost, measured at preset veryfast, CRF 23, video only, same input: a 60 s 1080p excerpt of the Day 4 lecture 1,439,405 B with B-frames against 1,709,010 B without (+18.7%); a 30 s synthetic 720p `testsrc2` clip 9,602,854 B against 9,918,313 B (+3.3%). One run each, one machine.
- **Copy path.** After copying the video, the engine computes the skew from the output's edit lists. If it exceeds the bound, the video is redone as a transcode (`bframes=0`) and `decision.reasons` in `normalise.json` says why (`copied video would show N ms of A/V skew ...`). Copied H.264 with B-frames is thus transcoded.
- **Post-verify** (`verify_outputs`): start times within one frame of 0, no empty edit longer than one frame, and the ignored-edit-list skew within the bound. Any failure is `SYNC_CHECK_FAILED`; the measured skew is stored as `verify.ignored_edit_list_skew_s`.
- **Relaxed empty-edit rule (accepted).** Empty edits of at most one frame are allowed. Common sources carry a few milliseconds (Opus pre-skip -7 ms, an MPEG-TS offset of 21 ms, an AV1 delay of 40 ms); the skew bound above still covers them.
- `NORMALISER_VERSION` is "4", so existing lectures re-normalise on a re-upload of the same bytes.
- **Link ingestion is covered.** `ingest_link` and `ingest_file` both call `normalise_media`; there is no second path.

## Alternatives considered

- **Keep the copy and document the browser limitation.** Rejected: every citation seeks `video.mp4`, and a 1.5 s shift is visible.
- **Rewrite only the container timestamps (`-itsoffset`, `-copyts`).** Rejected for audio: without a sample-accurate pad the track still starts late and needs an edit; the re-encode with leading silence is exact. Rejected for video: padding needs a decoded frame to hold.
- **Always transcode both streams.** Rejected: slow and lossy for the great majority of files that need none of it.

## Consequences

- A source with a late audio stream costs an AAC re-encode (seconds); a late video stream, or copy-eligible H.264 with B-frames (the common case for OBS and phone recordings), costs a full video transcode and about 19% more bitrate on lecture footage.
- Measured after the change, with edit lists ignored (offset beep minus flash, limit 40 ms): control +21.4 ms, delayed audio +20.7, delayed video +21.4, MPEG-TS offset +21.4, HEVC+Opus with a 0.7 s audio delay +22.4, HEVC+Opus +28.4, copied H.264 with B-frames +21.4. Before the B-frame change the same cases showed -58.6, -57.6 and -51.6 ms.
- The 21 ms in most rows is the AAC priming edit, which is under a frame at 25 fps.

## Evidence

`backend/tests/integration/test_media_engine.py` (`test_flash_and_beep_coincide` and `..._when_edit_lists_are_ignored` over seven clips, `test_copy_eligible_clip_with_bframes_is_detected_and_transcoded`, `test_no_track_of_any_sync_clip_has_a_long_empty_edit`, the two `test_post_verify_rejects_...`), `backend/tests/unit/test_media_policy.py`, `tools/m2_verify` check 9, and `docs/evidence/m2/`. The in-browser result is step 11 of `docs/evidence/m2/BROWSER_CHECKLIST.md`, filled in by hand.

## Gate / revisit when

Revisit if the transcode cost (about 19% bitrate, and time for copy-eligible files with B-frames) proves too high once the browser checklist shows whether browsers honour non-empty edits: if they all do, the invariant could drop the B-frame term.
