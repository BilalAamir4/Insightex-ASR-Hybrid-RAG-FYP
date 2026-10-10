# M4 Whisper WER/CER gate: results

**L2 WER is a comparison metric between configs on this lecture, not an absolute accuracy figure. It must not be quoted as the system's ASR accuracy.**

Audio: `/home/bilal_aamir/insightex-data/eval/day04_batch_vs_online/eval/lecture_full.wav` (688 s). Reference: `/home/bilal_aamir/insightex-data/eval/day04_batch_vs_online/eval/manual_roman.txt` (2423 words, 0 `[unclear]` wildcards).

## Table

| config | L1 WER | L1 CER | L2 WER | L2 CER | L1 S/D/I | L2 S/D/I | dropped speech (longest gap) | Latin share (raw) | warm RTF | peak VRAM | detected language |
|---|---|---|---|---|---|---|---|---|---|---|---|
| medium_ur | 92.9% | 60.2% | 68.4% | 47.3% | 1491/735/25 | 804/764/89 | 21.9% (32.1s) | 5.6% | 0.240 | 3294 MiB | ur (1.000) |
| medium_auto | 67.6% | 49.4% | 67.6% | 53.0% | 1169/445/25 | 1168/445/25 | 5.1% (2.1s) | 100.0% | 0.049 | 2974 MiB | hi (0.884) |
| large-v3_ur | 57.7% | 18.7% | 24.7% | 6.6% | 1238/36/125 | 424/43/132 | 1.9% (1.0s) | 39.4% | 0.119 | 4638 MiB | ur (1.000) |
| large-v3_auto | 27.9% | 13.4% | 18.2% | 11.1% | 480/190/6 | 246/190/6 | 5.7% (10.2s) | 40.4% | 0.180 | 5310 MiB | hi (0.932) |

Not evaluated: large-v3-turbo x ur, large-v3-turbo x auto (large-v3-turbo is not in the offline cache; skipped by decision).
Hypothesis words after the last aligned reference word are excluded (cut tail): medium_ur 4, medium_auto 1, large-v3_ur 2, large-v3_auto 1 tokens (L2 alignment).
Peak VRAM = max `nvidia-smi` memory.used during the whole run (load + warm-up + transcription) minus the idle baseline (1497 MiB, includes the Windows desktop). Warm RTF = transcribe seconds / audio seconds after one discarded warm-up run.

## Flags (thresholds are starting values; a human confirms disqualification)

- `medium_ur`: dropped speech 21.9% > 2.0%; uncovered speech gap 32.1s >= 10.0s; 9 reference words deleted in a row (~120s gap at 375s)
- `medium_auto`: dropped speech 5.1% > 2.0%; Latin-script share 100.0% is 94 pp above the lowest config (translation drift?); Latin-script stretch of 1966 words
- `large-v3_ur`: Latin-script share 39.4% is 34 pp above the lowest config (translation drift?); Latin-script stretch of 65 words
- `large-v3_auto`: dropped speech 5.7% > 2.0%; uncovered speech gap 10.2s >= 10.0s; 41 reference words deleted in a row (~10s gap at 287s); Latin-script share 40.4% is 35 pp above the lowest config (translation drift?); Latin-script stretch of 65 words

## Bootstrap and tie rule (on L2 WER)

- **all configs**: best by L2 WER = `large-v3_auto`, runner-up = `large-v3_ur`. WER(best) - WER(runner-up) at L2 = -6.48 pp, 95% CI [-11.68, -0.50] pp (10000 paired resamples of 49 blocks of ~50 reference words, seed 12345). CI includes 0: **no**. Best by L2 CER = `large-v3_ur` (L2 WER and CER DISAGREE, treated as a tie). **Verdict: TIE.** For information, L1: -29.84 pp, CI [-35.18, -23.66].

- unflagged configs: none.

## Dropped speech detail

Independent energy VAD ({'frame_ms': 25, 'hop_ms': 10, 'above_noise_db': 12.0, 'noise_percentile': 10, 'fill_gap_s': 0.3, 'min_speech_s': 0.2, 'gap_merge_s': 0.5}); threshold -55.4 dBFS on this file; speech = 642 s of 688 s.

| config | speech s | uncovered s | longest uncovered gap | deleted reference runs >= 8 words (L2 alignment) |
|---|---|---|---|---|
| medium_ur | 642 | 140.8 | 32.1s | ref 61-74 (14 words, audio ~19s to ~19s); ref 145-156 (12 words, audio ~57s to ~57s); ref 158-181 (24 words, audio ~57s to ~59s); ref 463-492 (30 words, audio ~137s to ~143s); ref 555-563 (9 words, audio ~167s to ~168s); ref 1162-1198 (37 words, audio ~352s to ~352s); ref 1226-1236 (11 words, audio ~359s to ~360s); ref 1270-1442 (173 words, audio ~374s to ~374s); ref 1444-1453 (10 words, audio ~374s to ~374s); ref 1456-1641 (186 words, audio ~375s to ~375s); ref 1645-1700 (56 words, audio ~375s to ~375s); ref 1702-1710 (9 words, audio ~375s to ~495s); ref 1943-1956 (14 words, audio ~564s to ~564s); ref 2058-2074 (17 words, audio ~597s to ~597s); ref 2231-2241 (11 words, audio ~640s to ~640s); ref 2249-2277 (29 words, audio ~650s to ~650s) |
| medium_auto | 642 | 32.5 | 2.1s | ref 253-260 (8 words, audio ~80s to ~80s); ref 322-331 (10 words, audio ~102s to ~102s); ref 1115-1124 (10 words, audio ~330s to ~330s); ref 2008-2017 (10 words, audio ~576s to ~576s) |
| large-v3_ur | 642 | 12.5 | 1.0s | none |
| large-v3_auto | 642 | 36.6 | 10.2s | ref 157-182 (26 words, audio ~52s to ~52s); ref 956-996 (41 words, audio ~287s to ~298s); ref 1181-1236 (56 words, audio ~363s to ~363s); ref 2324-2362 (39 words, audio ~659s to ~659s) |

## Translation drift (raw output, before romanisation)

Reference English-term share: n/a (no English lexicon available; approved). Compared across configs instead.

- `medium_ur`: 5.6% of 1737 words in Latin script. Longest Latin stretches: 8 words @ 161s: "there is no incremental training Aug poker training" | 7 words @ 128s: "so that other people can use it" | 6 words @ 107s: "one of them is batch learning"
- `medium_auto`: 100.0% of 1966 words in Latin script. Longest Latin stretches: 1966 words @ 0s: "Hello guys, welcome to my YouTube channel, this is days of machine learning and we are int"
- `large-v3_ur`: 39.4% of 2481 words in Latin script. Longest Latin stretches: 65 words @ 431s: "batch learning is where you train your machine learning model with your entire data there " | 50 words @ 203s: "this is called batch learning where you take up your entire data you train your machine le" | 37 words @ 0s: "Hello guys, welcome to my YouTube channel This is days of machine learning and we are into"
- `large-v3_auto`: 40.4% of 2216 words in Latin script. Longest Latin stretches: 65 words @ 431s: "batch learning is where you train your machine learning model with your entire data, there" | 51 words @ 203s: "so this is called batch learning, where you take up your entire data, you train your machi" | 37 words @ 0s: "Hello guys, welcome to my YouTube channel This is days of machine learning and we are into"

## Normalisation

L2 collision rate on the reference: 78/555 distinct words = 14.1% (see `refwords.py` for the groups). Energy VAD speech share on the 30 s clip: 96.4% (see `vad_clip30s.md`).

## Parameters (identical for every config)

- faster-whisper 1.2.1, device cuda, compute_type float16
- explicit: {'task': 'transcribe', 'beam_size': 5, 'vad_filter': True, 'word_timestamps': True}
- resulting transcription options: {'beam_size': '5', 'best_of': '5', 'patience': '1', 'length_penalty': '1', 'repetition_penalty': '1', 'no_repeat_ngram_size': '0', 'log_prob_threshold': '-1.0', 'no_speech_threshold': '0.6', 'compression_ratio_threshold': '2.4', 'condition_on_previous_text': 'True', 'prompt_reset_on_temperature': '0.5', 'temperatures': '[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]', 'initial_prompt': 'None', 'prefix': 'None', 'suppress_blank': 'True', 'suppress_tokens': '(1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93, 359, 503, 522, 542, 873, 893, 902, 918, 922, 931, 1350, 1853, 1982, 2460, 2627, 3246, 3253, 3268, 3536, 3846, 3961, 4183, 4667, 6585, 6647, 7273, 9061, 9383, 10428, 10929, 11938, 12033, 12331, 12562, 13793, 14157, 14635, 15265, 15618, 16553, 16604, 18362, 18956, 20075, 21675, 22520, 26130, 26161, 26435, 28279, 29464, 31650, 32302, 32470, 36865, 42863, 47425, 49870, 50254, 50258, 50358, 50359, 50360, 50361, 50362)', 'without_timestamps': 'False', 'max_initial_timestamp': '1.0', 'word_timestamps': 'True', 'prepend_punctuations': '\'"\\\'“¿([{-\'', 'append_punctuations': '\'"\\\'.。,，!！?？:：”)]}、\'', 'multilingual': 'False', 'max_new_tokens': 'None', 'clip_timestamps': '[0.0]', 'hallucination_silence_threshold': 'None', 'hotwords': 'None'}
- VAD options: VadOptions(threshold=0.5, neg_threshold=None, min_speech_duration_ms=0, max_speech_duration_s=inf, min_silence_duration_ms=2000, speech_pad_ms=400)
- warm-up: one discarded transcription of the 30 s clip per run (model loaded once per config subprocess)
- romanisation: uroman, word by word; L1/L2 per `textnorm.py`; alignment per `gate_metrics.py`; CER is computed on space-free strings (exact Levenshtein) after dropping wildcard-absorbed and trimmed tokens

Note: the VAD pause check on the 30 s clip (pauses near 7.6-8.1 s and 16.9-17.5 s) was skipped by decision; no decision depends on it.
Run-to-run variation of the winner: `variance.md`.
