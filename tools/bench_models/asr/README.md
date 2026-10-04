# tools/bench_models/asr

**Purpose:** Whisper benchmarks: 10-minute extraction and transcription (process_a_whisper.py), cold/warm benchmark (verify_6a_whisper.py), medium vs large-v3 speed and temperature-fallback investigation (whisper_anomaly_audit.py).

**How to run:** `bash scripts/run_in_env.sh python tools/bench_models/asr/<script>.py`. GPU job; one at a time; free VRAM first.

**Inputs:** `$INSIGHTEX_DATA/eval/day04_batch_vs_online/raw/lecture_test.mp4`, `.../eval/clip_30s.wav`.

**Outputs:** `lecture_first10min.wav`, `whisper_large_v3_first10min.json` in the eval folder; T3 log under `$INSIGHTEX_DATA/logs/env_audit/followup`.

**Status:** Kept: the Whisper checkpoint decision is pending (waits on WER). verify_6a_whisper.py is kept as a candidate source of warm-run numbers that were never shown.

Standalone tool: it must not import from `backend/`.
