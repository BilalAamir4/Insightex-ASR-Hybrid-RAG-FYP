# tools/eval_wer

**Purpose:** the M4 Whisper WER/CER gate. It compares faster-whisper checkpoint x language configs on one lecture against a human-typed Roman reference and decides the ASR checkpoint and language setting (ADR-0039).

**Superseded:** the old Gemini-transliteration pipeline (Whisper Urdu script, Gemini transliteration, hand-fixed spelling) and its numbers are superseded. `wer_eval.py` for that pipeline was never added to this repository, so there is nothing to mark legacy here.

## Rerun end to end (one command)

```bash
D=~/insightex-data/eval/day04_batch_vs_online
bash ~/insightex/scripts/run_in_env.sh python ~/insightex/tools/eval_wer/run_gate.py \
  --audio $D/eval/lecture_full.wav --reference $D/eval/manual_roman.txt \
  --warmup-audio $D/eval/clip_30s.wav --out ~/insightex/tools/eval_wer/results/m4
```

`--reuse` re-scores existing `raw.json` files without running Whisper. Paths are arguments, nothing is hardcoded. No Ollama model may be loaded (the tool aborts if one is). Each config runs in its own subprocess, about 12 minutes in total on the RTX 3070.

## Inputs

- Audio: the full 688 s Day 4 lecture. It was extracted from `$D/raw/lecture_test.mp4` with the M2 normaliser's audio arguments (`media/engine.py: audio_args`), run directly on the source mp4:
  `ffmpeg -i lecture_test.mp4 -map 0:a:0 -af aresample=async=1:first_pts=0 -ac 1 -ar 16000 -c:a pcm_s16le -f wav lecture_full.wav`
  The older `lecture_first10min.wav` is cut at 600 s while the reference covers the whole lecture, so it must not be used with this reference.
- Reference: `manual_roman.txt` (Roman script, typed while listening, not time-aligned). `[unclear]` spans are wildcards in the aligner (this reference has none).

## Method (details in `results/m4/results.md`)

- Configs: medium and large-v3, each `ur` and auto-detect; `task="transcribe"`, beam 5, `vad_filter`, `word_timestamps`, float16. large-v3-turbo runs only if it is already in the offline cache (it was not).
- Romanisation: uroman, word by word. `textnorm.py`: L1 (lowercase, strip punctuation, collapse repeats) and L2 (phonetic key with a final-vowel class). **The L2 rules are frozen** (commit `c883b9e`).
- `gate_metrics.py`: word alignment with wildcards, WER/CER with S/D/I, energy-VAD dropped speech, deleted runs of 8 or more words, Latin-script drift, paired block bootstrap (blocks of ~50 words, 10,000 resamples, seed 12345).
- `flagged.py`: side-by-side passages for flagged configs. `refwords.py`: frequent reference words and L2 collision groups. `preview.py`: raw / romanised / L1 / L2 view of one raw.json. `test_gate.py`: synthetic checks (`python test_gate.py`).

## Outputs (`results/m4/`)

`results.md`, `decision.md`, `flagged.md`, `samples.md`, `vad_clip30s.md`, `reference_l1.txt`, `reference_l2.txt`, `preview_stop1/` (stop-point-1 evidence of medium auto translating), and per config `<config>/raw.json`, `romanised.txt`, `normalised_l1.txt`, `normalised_l2.txt`.

**L2 WER is a comparison metric between configs on this lecture, not an absolute accuracy figure; do not quote it as the system's ASR accuracy.**

Standalone tool: it must not import from `backend/`.
