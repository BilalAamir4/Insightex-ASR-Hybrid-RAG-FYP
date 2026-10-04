# Migration report (4 October 2026)

Moved the Insightex code, docs and data from `/mnt/e/FYP` into `~/insightex` (git, branch `main`, no remote) and `~/insightex-data`. Originals on `E:\FYP` are untouched and remain the backup. Details and decisions: `MIGRATION_PLAN.md` (repo root).

## What moved where
- Code, tools, scripts, docs: `tools/env_audit/*` split into `tools/audit_env/`, `tools/bench_models/{asr,embedding,llm,loadtimes}/`, `tools/probe_ollama/`, `scripts/` (`run_in_env.sh`, `windows/start_ollama.ps1`, `windows/run_probe.ps1`); `tools/vl_probe/probe.py` to `tools/probe_paddleocr_vl/`; `ENV_AUDIT_REPORT.md` (rewritten), `Embedding Report.md` (renamed `Embedding_Report.md`), `OCR_report.md`, `data/frames/out/REPORT.md` (now `vl_probe_REPORT.md`), `STRUCTURE_AUDIT.md` (now `PRE_MIGRATION_AUDIT.md`) to `docs/reports/`.
- Archived evidence: `docs/reports/embedding_bakeoff/` (`results_seq1024/`, `queries.csv`, `embed_bakeoff.py`, `doc_updates.md`, `window_comparison.md`, README).
- Data (sha256-verified, 32 files): `~/insightex-data/eval/day04_batch_vs_online/{raw,eval}`, `eval/frames/{eq1.png,out/}`, `logs/env_audit/{followup,followup2}/`. `db/` and `workspaces/` created empty.
- New: package skeleton, `config/`, `docs/MODELS.md`, ADR 0001, draft contracts, runbooks, tool READMEs, `scripts/verify_env.sh`, `pyproject.toml`, `.gitignore`, `.gitattributes`.
- `requirements.lock.txt`: byte-identical copy.

## Removed and how to recover
Not carried into the working tree: the old `embedding/` test suite, `selftest/`, the 512-token `results/` (except `doc_updates.md` and `window_comparison.md`), `embedding/requirements.lock.txt`, the duplicate SRT, `run_T*`/`run_F*` runners (except `run_F2_repro.py`, `run_F7_check.py`), `fail_*`, `update_shell_env.py`, `print_bashrc.sh`, `test_whisper*.py`, `verify_6d_faiss_networkx.py`, `smoke_*.py`, `__pycache__`, `.pytest_cache`. `embedding/.venv` was never copied.
Recovery: `git show import-baseline:_legacy_import/<original path>` (the baseline holds 126 files copied verbatim), or the untouched originals on `E:\FYP`.

## Environment variable diff
| Variable | Before | After |
|---|---|---|
| `HF_HOME`, `PIP_CACHE_DIR`, `TORCH_HOME`, nvidia site path | `/home/bilal_aamir/...` | `$HOME/...` |
| `INSIGHTEX_ROOT` | `/mnt/e/FYP` | removed |
| `INSIGHTEX_HOME`, `INSIGHTEX_DATA`, `INSIGHTEX_MODEL_CACHE_MASTER` | unset | `$HOME/insightex`, `$HOME/insightex-data`, `/mnt/e/FYP/cache` |
| `_INSIGHTEX_ENV_LOADED`, `HF_HUB_OFFLINE`, `OLLAMA_BASE_URL`, `LD_LIBRARY_PATH` logic | | unchanged |
| `OLLAMA_MODELS`, `OLLAMA_HOST` | | unchanged |
Startup files: `~/.bashrc` line removed; `~/.profile` sources `$HOME/insightex/env/insightex_env.sh` once. Backups: `~/.bashrc.bak-20261004-173323`, `~/.profile.bak-20261004-173323`.

## Check results (Phase 3)
| # | Check | Result |
|---|---|---|
| 1 | Login-shell env, sourced once | PASS (1 execution in `bash -lc` and `bash -lic`; each variable once; 16 `LD_LIBRARY_PATH` entries, 0 duplicates) |
| 2 | Path grep | Partial: no stray `/home/`, `bilal_aamir` or `/mnt/e` code paths. Remaining hits are data-folder names via `$INSIGHTEX_DATA`, `loadtimes_results.json` (evidence), and the intended `E:\FYP\LLMs` / `/mnt/e/FYP/cache` values |
| 3 | `import insightex` with `PYTHONPATH=backend/src` | PASS |
| 4 | `ruff check .` | NOT RUN: ruff not installed anywhere; nothing was installed |
| 5 | `pytest --collect-only` | PASS (0 tests, no errors) |
| 6 | Syntax | PASS: 9 `bash -n`, 24 Python compiles, 2 `.ps1` parse with 0 errors; no CRLF in `.sh`/`.py` |
| 7 | `/api/tags` lists `qwen3.5:latest` | PASS |
| 8 | Lockfile sha256 | PASS, `f120c37f6dbb07387711b5b065ce0106a320b63b16d9f60acc4f4d1a599daba4`, `cmp` identical |
| 9 | `run_in_env.sh` GPU-free import | PASS (`ok`); nvidia-smi 1446 MiB before and after |
| 10 | git state | see final `git status` in the session |
Extra: read-only kept scripts (`check_login_env.sh`, `check_paths.sh`, `check_shell_env.sh`, `check_files_integrity.py`, `check_env_vars.py`, `check_imports.py`, `check_av.py`, `check_ollama_endpoint.py`, via `verify_env.sh`) all ran and printed the new paths; VRAM unchanged (1487 to 1480 MiB, no model loaded).

## Judgment calls
`verify_6b_loadtimes.py` DrvFS path now the master HF cache (was `LLMs`); `run_F7_check.py` lost its Windows-path fallback; `run_loadtimes_benchmark.py` writes results next to itself; `check_shell_env.sh` keeps a hardcoded Windows user path for `.wslconfig`; `run_probe.ps1` derives the data dir through `wslpath -w` (not exercised, it is a GPU probe).

## Untouched open items
Ollama call contract; LLM choice; Whisper checkpoint choice (waits on WER); textbook selection; PaddleOCR-VL 30-frame bake-off; `.wslconfig` backup (`.wslconfig.bak` does not exist); supervisor-name and proposal-date discrepancies; "Bilal Aamir/Amir" spelling; `~/.paddlex` (about 1,985 MB) vs `E:\FYP\cache\paddlex` (about 302 MB); the 4,026 vs 4,532 MiB Whisper medium VRAM figure; ruff not installed; `run_probe.ps1` and the loadtimes orchestrator not exercised.
