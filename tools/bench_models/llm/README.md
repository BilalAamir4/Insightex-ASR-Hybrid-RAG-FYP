# tools/bench_models/llm

**Purpose:** Ollama call-contract and API verification, VRAM peak monitoring (verify_6c_ollama.py).

**How to run:** `bash scripts/run_in_env.sh python tools/bench_models/llm/verify_6c_ollama.py`. Needs Ollama; GPU job.

**Inputs:** `$INSIGHTEX_DATA/eval/day04_batch_vs_online/eval/manual_roman.txt`.

**Outputs:** Console output.

**Status:** Kept; the LLM choice is pending.

Standalone tool: it must not import from `backend/`.
