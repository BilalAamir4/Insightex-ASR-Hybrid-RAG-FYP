# tools/bench_models/embedding

**Purpose:** Load and VRAM check for BAAI/bge-m3 (verify_6b_bge.py).

**How to run:** `bash scripts/run_in_env.sh python tools/bench_models/embedding/verify_6b_bge.py`. GPU job.

**Inputs:** bge-m3 in `$HF_HOME`.

**Outputs:** Console output.

**Status:** Kept as a regression check. The embedding decision itself is closed (`docs/adr/0001-bge-m3.md`).

Standalone tool: it must not import from `backend/`.
