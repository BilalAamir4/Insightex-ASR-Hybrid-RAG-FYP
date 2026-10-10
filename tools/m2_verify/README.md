# M2 exit-criterion verification

`m2_verify.py` checks the M2 exit criterion on the real machine: the Day 4 lecture normalises through the HTTP upload path, and odd files are rejected cleanly with specific codes.

Standalone: it never imports from `backend/src/insightex`. It talks to the running server over HTTP (standard library only), calls `python -m insightex.cli ingest-file` by subprocess, and uses `ffmpeg`/`ffprobe` for fixtures and measurements.

## Run

```bash
bash ~/insightex/scripts/dev_run.sh          # terminal 1: worker + API on 127.0.0.1:8000
bash ~/insightex/scripts/run_in_env.sh python ~/insightex/tools/m2_verify/m2_verify.py \
    --day4 ~/insightex-data/eval/day04_batch_vs_online/raw/lecture_test.mp4    # terminal 2
# options: --base-url http://127.0.0.1:8000  --data-dir $INSIGHTEX_DATA  --job-timeout 900  --out-dir DIR  --keep
```

Use an idle worker and an empty staging folder: checks 7 and 10 expect `<data>/staging` to be empty. The run deletes the lectures it created (unless `--keep`).

## Checks (13)

1 server reachable; 2 Day 4 uploaded with progress and the job completes; 3 artifacts (h264/aac with `moov` before `mdat`, `audio.wav` pcm_s16le 16 kHz mono, thumbnail); 4 durations (|wav-mp4| <= 1 s, |mp4-source| <= max(2 s, 1%)); 5 `source.json` (kind `upload`, via `http`, SHA-256) and `normalise.json` (decision, `normaliser_version`, warnings list); 6 re-upload is deduplicated with no new job; 7 audio-only, video-only, text-as-mp4 and 5 s clip end with `NO_VIDEO_STREAM`, `NO_AUDIO_STREAM`, `NOT_A_VIDEO`, `TOO_SHORT`, leave no lecture directory and no staging file; 8 HEVC fixture accepted with `video=transcode`; 9 flash/beep fixture with audio delayed 1.5 s: |flash-beep| <= one frame (40 ms at 25 fps); 10 raw-socket upload cut at half: no staging file within 5 s, server healthy, busy slot freed; 11 missing rights header -> 400; 12 oversize `Content-Length` -> 413 in under 1 s without sending a body; 13 CLI `ingest-file` on a small fixture succeeds.

Exit code 0 only if every check passes. Evidence goes to `docs/evidence/m2/`: `m2_verify_<UTC>.json` and `.log` (checks, timings, decision), and ffprobe JSON of the Day 4 `video.mp4` and `audio.wav`. The Day 4 media and transcript are never written to the repo.

`make_browser_fixtures.sh` builds the files for `docs/evidence/m2/BROWSER_CHECKLIST.md`.
