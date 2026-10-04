# After-restart checklist

Derived from the rules in `CLAUDE.md` and `docs/reports/ENV_AUDIT_REPORT.md`. The ordering below has not been tested after a real reboot (unverified).

1. **Ollama (Windows PowerShell):** run `scripts/windows/start_ollama.ps1` (sets `OLLAMA_MODELS=E:\FYP\LLMs`, `OLLAMA_HOST=127.0.0.1:11434`, runs `ollama serve`). Keep that window open.
2. **Endpoint (WSL):** `curl -s http://localhost:11434/api/tags` should list `qwen3.5:latest`.
3. **Environment (WSL, new login shell):** `echo $INSIGHTEX_HOME $INSIGHTEX_DATA $HF_HUB_OFFLINE` should print the planned values; the env script is sourced once by `~/.profile`.
4. **VRAM baseline:** `nvidia-smi` memory should be near the desktop idle (the audit saw 994 to 1,167 MiB). If a model is loaded, run `ollama ps` and `ollama stop <model>`.
5. **Read-only checks:** `bash scripts/verify_env.sh`.
6. **GPU work:** only via `bash scripts/run_in_env.sh python ...`, one CUDA stage at a time.
7. **If the WSL disk or caches look wrong:** verify cache hashes with `bash scripts/run_in_env.sh python tools/audit_env/run_F7_check.py` (master vs runtime). `.wslconfig` backup status is an open item (not checked here).
