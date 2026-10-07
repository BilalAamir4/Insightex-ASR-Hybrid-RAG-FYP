# Setup runbook

Sources: `CLAUDE.md` and `docs/ENVIRONMENT.md`. Steps marked *unverified* are stated there but were not re-run when this runbook was written. Starting from a blank machine has not been tested.

## Layout

- Code and docs: `~/insightex` (WSL ext4, git repo, branch `main`, no remote).
- Runtime data: `~/insightex-data` (outside the repo).
- Heavy storage stays on the Windows drive: `E:\FYP\wsl`, `E:\FYP\docker`, `E:\FYP\cache` (master model cache), `E:\FYP\LLMs` (Ollama models). Nothing project-related should grow on C:.

## Python environments (WSL)

- Main venv `~/envs/insightex` (Python 3.12, torch cu128, faster-whisper, sentence-transformers, faiss-cpu, networkx), pinned in `requirements.lock.txt`.
- PaddleOCR has its own venv `~/envs/paddleocr-vl`.
- Do not create or modify venvs as part of repo work; ask first (torch installs need approval).

## Environment script

`env/insightex_env.sh` sets `INSIGHTEX_HOME`, `INSIGHTEX_DATA`, `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE=1`, `OLLAMA_BASE_URL`, `PIP_CACHE_DIR`, `TORCH_HOME` and `LD_LIBRARY_PATH` (CUDA libraries from the venv's `nvidia-*` packages, deduplicated). `~/.profile` sources it once for login shells. See `env/.env.example`.

## Running GPU work

Always through the wrapper (otherwise faster-whisper fails at inference time with `libcublas.so.12 is not found`):

```bash
bash ~/insightex/scripts/run_in_env.sh python <script.py> ...
```

Run commands from a WSL shell, not nested through PowerShell (`wsl -- bash -lc "..."` breaks `$` and `&&`). Never run two CUDA stages at once; free VRAM first (`ollama ps`, then `ollama stop <model>`).

## Model caches

- Runtime cache: `~/cache/huggingface` on ext4. Master copy: `E:\FYP\cache`. Do not point caches at `/mnt/e` (DrvFS loads are 3.5x to 7.4x slower).
- `HF_HUB_OFFLINE=1` is global. To add a model (ask first; this downloads): download with `HF_HUB_OFFLINE=0 HF_HOME=/mnt/e/FYP/cache/huggingface`, `cp -ru` it into `~/cache/huggingface/hub/`, then verify hashes with `tools/audit_env/run_F7_check.py`.

## Ollama

Runs on the Windows host, bound to `127.0.0.1:11434`, reached from WSL as `localhost` (mirrored networking in `%UserProfile%\.wslconfig`). Models are stored in `E:\FYP\LLMs` (Windows user variable `OLLAMA_MODELS`). Start it with `scripts/windows/start_ollama.ps1`. Never set `OLLAMA_HOST=0.0.0.0`.

Batch call settings: see `docs/adr/0002-ollama-call-contract.md` (`chat_json`: JSON Schema `format`, `think: false`, `keep_alive: "10m"`, `num_ctx` required with default 8192, `num_predict` default 1024, `temperature` 0). At the end of a batch call `unload()` in a `finally` block.

## Checks

`bash scripts/verify_env.sh` runs the read-only, GPU-free checks.
