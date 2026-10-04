# tools/bench_models

**Purpose:** Model benchmarks kept for pending decisions and as regression checks.

**How to run:** See the sub-folder READMEs: asr/, embedding/, llm/, loadtimes/.

**Inputs:** See sub-folders.

**Outputs:** See sub-folders.

**Status:** Kept. Some scripts duplicate logic (VRAM sampler, Whisper test loads); intentionally not refactored.

Standalone tool: it must not import from `backend/`.
