# tools/ — diagnostics, audits, benchmarks, evaluation

- Every script here is standalone and must never import from `backend/` (the `insightex` package). When a tool's logic is needed in production, port it into `backend/src/insightex/` and leave a note saying where it went.
- Naming: `check_*` / `verify_*` for environment checks, `bench_*` for benchmarks, `eval_*` for metrics (WER and retrieval).
- Write results to files (CSV/JSON) and report numbers from those files, never from memory or console scrollback.
- Evaluation integrity:
  - Never derive gold labels from the SRT being evaluated.
  - Compute WER against a transcription, not a translation. Confirm `task="transcribe"` first.
  - Count dropped segments explicitly.
- Run GPU tools through `scripts/run_in_env.sh` and follow the VRAM contract in the root CLAUDE.md.
