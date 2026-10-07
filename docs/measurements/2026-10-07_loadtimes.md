# Model load times and Whisper speed, first boot after a full Windows restart (2026-10-07)

Windows booted 23:30:30; WSL VM up 23:31:12. All runs below were made after that boot, before any model had been read from the WSL ext4 cache (`~/cache/huggingface/hub`), with Ollama up and idle (no model resident). RTX 3070, host idle baseline 600 to 1,273 MiB (Windows desktop, varies by the minute). Single runs; no repeats.

## Load times (seconds)

| Model | Loader | Cold: first load after boot | Warm: immediate reload (same process) | Run 2, first load (cache already hot) | Run 2, reload |
|---|---|---|---|---|---|
| whisper medium, fp16 | faster-whisper (`verify_6b_loadtimes.py`) | 4.35 | 0.78 | 1.31 | 0.69 |
| whisper large-v3, fp16 | faster-whisper (`verify_6b_loadtimes.py`) | 7.92 | 1.78 | 2.41 | 1.68 |
| bge-m3 (1024-d) | sentence-transformers (`m0_extra_timings.py bge`) | 6.48 | 1.59 | not run | not run |

- "Cold" is the natural post-boot page-cache state. The page cache was **not** dropped (`drop_caches` needs `sudo`); that is why run 2's first load is already warm. Run 2 exists only as an extra warm data point.
- Cold-to-warm speedup, run 1: medium 5.6x, large-v3 4.4x, bge-m3 4.1x.
- Earlier figures (2 to 3 Oct, ENV audit, ext4): medium 3.76 / 0.66, large-v3 8.37 / 2.03, bge-m3 6.25 / 1.70 (cold / warm). Today's numbers are in the same range. The older ones were measured with a forced cache drop, today's after a reboot.

## Whisper warm speed on the Day 4 audio (speed only, not accuracy)

Audio: `lecture_first10min.wav`, 600.0 s. Settings: `language=ur`, `task=transcribe`, `beam_size=5`, `temperature=0.0`, `vad_filter=True`, fp16, CUDA. One untimed warm-up transcription of `clip_30s.wav` first, then one timed pass over the full 10 minutes (decoding generator fully consumed). Real-time factor (RTF) = decode seconds / audio seconds.

| Model | Model load (s) | Decode time (s) | RTF | x real time | Segments |
|---|---|---|---|---|---|
| medium | 1.32 | 27.98 | 0.0466 | 21.4x | 203 |
| large-v3 | 2.12 | 71.81 | 0.1197 | 8.4x | 554 |

- The segment counts differ a lot (203 vs 554). This file says nothing about which transcript is better; WER is M4. Checkpoint and language settings are still open decisions.
- For comparison, the 3 Oct audit measured large-v3 at 9.00x real time on the same lecture (carried over, not re-run) and 8.9x on a 30 s clip.

## What was run and how (deviations from the plain script)

- `tools/bench_models/loadtimes/verify_6b_loadtimes.py` was run **as written**, with two environment safeguards, and its source untouched:
  - `sudo` was replaced by a no-op on `PATH` (a password is required and CLAUDE.md says to ask before `sudo`), so no cache drop happened.
  - `INSIGHTEX_MODEL_CACHE_MASTER` was pointed at a nonexistent path so the script skipped its DrvFS (`/mnt/e`) comparison and did not read `E:\FYP\cache`.
- The script's bge-m3 step **failed** (`ModuleNotFoundError: No module named 'FlagEmbedding'`). That package is not in the lockfile and was not installed (no package changes without approval). Its README already said it had never been run. bge-m3 was therefore timed with sentence-transformers, which is what the pipeline uses, via the new standalone `tools/bench_models/loadtimes/m0_extra_timings.py` (also used for the Whisper RTF runs).
- The script's own "VRAM after" field read 4,432 MiB for medium because it samples before the subprocess exits; it is not a leak.
