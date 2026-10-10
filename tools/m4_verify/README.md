# M4 session 2 verification

`m4_verify.py` checks the M4 session 2 exit criterion on the real machine: the `asr` stage transcribes the Day 4 lecture through the real pipeline exactly like the accepted gate (ADR-0039), with per-lecture language selection (ADR-0040) and the stage design of ADR-0042.

Standalone: it never imports from `backend/src/insightex`. It starts **its own** API server (port 8011) and worker on an isolated data directory (`~/insightex-data/m4_verify_run`), so the real library is never touched, and drives them through the `insightex` CLI and the HTTP API. Both share the **real** GPU lease, so the one-CUDA-stage rule holds. The run directory is deleted at the end unless `--keep`.

## Run

```bash
bash ~/insightex/scripts/run_in_env.sh python ~/insightex/tools/m4_verify/m4_verify.py
# defaults: --day4 ~/insightex-data/eval/day04_batch_vs_online/raw/lecture_test.mp4
#           --clip .../eval/clip_30s.wav  --gate-raw tools/eval_wer/results/m4/large-v3_ur/raw.json
#           --gate-audio .../eval/lecture_full.wav  --port 8011  --job-timeout 1800  --out-dir docs/evidence/m4  --keep
```

It aborts (exit 2) before doing anything if a worker is running or the GPU lease is held, or if Ollama has a model loaded; the message names the model and the command to unload it (`ollama stop <model>`). It never stops Ollama itself. About 10 minutes on the RTX 3070 (Day 4 is normalised and transcribed twice).

## Checks (12; run in the order 1, 11, 2-4/7/9/10, 5, 12, 8, 6; reported in number order)

1. large-v3 (pinned snapshot) is in the offline HF cache; `insightex config validate` passes; the language list has `hindi` as the only tested entry and 99 untested.
2. Day 4 submitted with `hindi` (`ingest-file`) runs fetch, normalise, asr and produces `transcript.json` (valid against `docs/contracts/transcript.schema.json`, `whisper_language` `ur`) and `transcript.vtt`.
3. sha256 of the workspace `audio.wav` vs the gate input `lecture_full.wav` (reported EQUAL or DIFFERENT).
4. Equal audio: segment count, text and timestamps (0.001 s) identical to the gate's `large-v3_ur/raw.json`. Different audio: WARN with the number of differing segments.
5. Submitting Day 4 again with `hindi` is de-duplicated at submission: no job, no lease, no subprocess (worker log), under 60 s including the copy and hash.
6. Kill test: the Day 4 workspace is deleted and resubmitted; the worker is killed (SIGKILL) once ASR passes 10%; no Whisper child survives; no transcript file is in its final location at the kill, every transcript read during the run is complete JSON, no temp files remain; after a restart the job succeeds with attempts 2 and the same segments as check 2 (and the gate).
7. `nvidia-smi` memory.used 3 s after the Day 4 job is within 100 MiB of the reading before it.
8. Worker restarted with `INSIGHTEX__ASR__MIN_FREE_VRAM_MIB=999999`; the clip submitted as `urdu` fails with `INSUFFICIENT_VRAM` and a message giving free and needed MiB; the worker is still running.
9. All times within [0, duration], segment starts non-decreasing, word times inside their segment (0.5 s).
10. VTT cue count equals segment count; cue times match the JSON.
11. Missing and unknown language are rejected by the link API, the upload API and the CLI with `MISSING_LANGUAGE` / `UNKNOWN_LANGUAGE`; no job is queued and nothing is staged.
12. The 30 s clip (muxed with a test pattern into an mp4, because ingest needs a video stream) with `english` completes; `tier_at_processing` `untested`, `whisper_language` `en`, and the job document reports tier `untested`.

Exit code 0 only if no check fails and all 12 ran. Evidence: `docs/evidence/m4/m4_verify_<UTC>.json` and `.log` (checks, Day 4 stats, gate comparison, timings). Transcript text is never written to the evidence.
