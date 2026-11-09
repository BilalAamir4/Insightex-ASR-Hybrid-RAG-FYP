# After-restart checklist

Derived from the rules in `CLAUDE.md` and `docs/ENVIRONMENT.md`. The Ollama autostart and `verify_env.sh` steps were confirmed after a full Windows restart on 2026-10-07; the rest of the ordering is as written, not separately tested.

1. **Ollama (Windows):** it starts by itself at logon through the Task Scheduler task **`Insightex Ollama`** (runs `E:\FYP\start_ollama.ps1`, which logs to `E:\FYP\logs\ollama_serve.log`). Check that the task is **Running** (`(Get-ScheduledTask -TaskName 'Insightex Ollama').State`). If it is Ready, its server has exited: read the end of the log, then `Start-ScheduledTask -TaskName 'Insightex Ollama'`. **Never open the Ollama tray app** (`ollama app.exe`): it is a second launcher and it auto-updates. Never start a second instance by hand while the task is running.
2. **Endpoint and frozen version (WSL):** `curl -s http://localhost:11434/api/tags` should list `qwen3.5:latest` and `gemma4:e4b`; `python3 docs/evidence/m7/scripts/check_ollama_frozen.py` must print OK (Ollama 0.40.2, frozen for M7). On STOP, do no M7 run and tell Bilal.
3. **Environment (WSL, new login shell):** `echo $INSIGHTEX_HOME $INSIGHTEX_DATA $HF_HUB_OFFLINE` should print the planned values; the env script is sourced once by `~/.profile`.
4. **VRAM baseline:** `nvidia-smi` memory should be near the desktop idle (600 to 1,273 MiB seen on 2026-10-07; close GPU-heavy Windows apps first). If a model is loaded, run `ollama ps` and `ollama stop <model>`.
5. **Read-only checks:** `bash scripts/verify_env.sh`.
6. **GPU work:** only via `bash scripts/run_in_env.sh python ...`, one CUDA stage at a time.
7. **If the WSL disk or caches look wrong:** verify cache hashes with `bash scripts/run_in_env.sh python tools/audit_env/run_F7_check.py` (master vs runtime). `.wslconfig` backup status is an open item (not checked here).
