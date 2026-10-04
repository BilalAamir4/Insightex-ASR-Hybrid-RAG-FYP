# tools/eval_wer

**Purpose:** Word error rate evaluation of ASR output against the manual Roman-Urdu reference (decides the Whisper checkpoint).

**How to run:** Not written yet.

**Inputs:** ASR transcripts; `$INSIGHTEX_DATA/eval/day04_batch_vs_online/eval/manual_roman.txt`.

**Outputs:** WER tables.

**Status:** Planned. The tool is not in the repository yet. The Whisper checkpoint decision waits on it.

Standalone tool: it must not import from `backend/`.
