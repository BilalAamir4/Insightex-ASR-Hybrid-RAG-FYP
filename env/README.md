# env/

- `insightex_env.sh`: sourced from `~/.profile`. Sets the Insightex paths, `HF_HOME`, `HF_HUB_OFFLINE`, `OLLAMA_BASE_URL` and the CUDA `LD_LIBRARY_PATH`.
- `wslconfig.reference`: byte-for-byte copy (UTF-8 BOM and CRLF line endings kept) of the Windows file `C:\Users\Bilal Aamir\.wslconfig`. It is a reference only; the live file stays on Windows.
  - Copied on 2026-10-07. No original backup (`.wslconfig*`) was found next to it, so this copy is the only record.
  - It contains `networkingMode=mirrored`, which is how WSL reaches Ollama on Windows at `localhost:11434`.
