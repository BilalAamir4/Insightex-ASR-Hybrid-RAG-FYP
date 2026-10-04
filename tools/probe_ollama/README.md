# tools/probe_ollama

**Purpose:** Probes of the Ollama call contract (JSON Schema vs json format, context size, think flag, streaming, batch unload). The contract is unfinished.

**How to run:** Through the wrapper, e.g. `bash scripts/run_in_env.sh python tools/probe_ollama/ollama_contract.py`. Needs Ollama running. GPU job (model loads in Ollama); free VRAM first and run one at a time.

**Inputs:** `$INSIGHTEX_DATA/eval/day04_batch_vs_online/eval/whisper_large_v3_first10min.json` (ollama_contract.py, run_F2_repro.py).

**Outputs:** Logs under `$INSIGHTEX_DATA/logs/env_audit/followup` (T2.txt) and `followup2` (F2.txt).

**Status:** Kept because the call contract is unfinished. Scripts: ollama_contract.py, probe_ollama.py, probe_think.py, run_F2_repro.py, test_ollama_chat.py, test_ollama_json.py.

Standalone tool: it must not import from `backend/`.
