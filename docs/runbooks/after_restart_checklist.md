# After-restart checklist

Derived from the rules in `CLAUDE.md` and `docs/ENVIRONMENT.md`. The Ollama autostart and `verify_env.sh` steps were confirmed after a full Windows restart on 2026-10-07; the rest of the ordering is as written, not separately tested.

1. **Ollama (Windows):** it starts by itself at logon through the Task Scheduler task **`Insightex Ollama`** (runs `E:\FYP\start_ollama.ps1`). Check that the task is Running. **Manual start only as a fallback** if the task did not start it: run `E:\FYP\start_ollama.ps1` in Windows PowerShell (sets `OLLAMA_MODELS=E:\FYP\LLMs`, `OLLAMA_HOST=127.0.0.1:11434`, runs `ollama serve`) and keep that window open. Never start a second instance by hand while the task is running.
2. **Endpoint (WSL):** `curl -s http://localhost:11434/api/tags` should list `qwen3.5:latest`.
3. **Environment (WSL, new login shell):** `echo $INSIGHTEX_HOME $INSIGHTEX_DATA $HF_HUB_OFFLINE` should print the planned values; the env script is sourced once by `~/.profile`.
4. **VRAM baseline:** `nvidia-smi` memory should be near the desktop idle (600 to 1,273 MiB seen on 2026-10-07; close GPU-heavy Windows apps first). If a model is loaded, run `ollama ps` and `ollama stop <model>`.
5. **Read-only checks:** `bash scripts/verify_env.sh`.
6. **GPU work:** only via `bash scripts/run_in_env.sh python ...`, one CUDA stage at a time.
7. **If the WSL disk or caches look wrong:** verify cache hashes with `bash scripts/run_in_env.sh python tools/audit_env/run_F7_check.py` (master vs runtime). `.wslconfig` backup status is an open item (not checked here).
