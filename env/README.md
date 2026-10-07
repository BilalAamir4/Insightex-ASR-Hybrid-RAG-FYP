# env/

- `insightex_env.sh`: sourced from `~/.profile`. Sets the Insightex paths, `HF_HOME`, `HF_HUB_OFFLINE`, `OLLAMA_BASE_URL` and the CUDA `LD_LIBRARY_PATH`.
- `wslconfig.reference`: byte-for-byte copy (UTF-8 BOM and CRLF line endings kept) of the Windows file `C:\Users\Bilal Aamir\.wslconfig`. It is a reference only; the live file stays on Windows.
  - Copied on 2026-10-07. No original backup (`.wslconfig*`) was found next to it, so this copy is the only record.
  - It contains `networkingMode=mirrored`, which is how WSL reaches Ollama on Windows at `localhost:11434`.

## Verification (M0 exit)

`bash scripts/verify_env.sh` (a wrapper) or `bash scripts/run_in_env.sh python tools/verify_env.py` is the single entry point. Reports go to `$INSIGHTEX_DATA/env_reports/<timestamp>.json`. The older `tools/audit_env/check_*` scripts are diagnostics only.

- `requirements.lock.txt` deliberately omits the editable `insightex` install (this repo), and `pip freeze` omits `pip`, `setuptools` and `wheel`. The verifier ignores exactly those four.
- Ollama on Windows must be running first: `scripts/windows/start_ollama.ps1` (loopback only). For the cold-boot criterion it has to start automatically at Windows logon (Task Scheduler, set up by hand on the Windows side).
