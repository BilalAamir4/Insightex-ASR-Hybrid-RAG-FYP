# tools/audit_env

**Purpose:** Environment checks: shell variables, paths, imports, Ollama endpoint, file integrity, sequential VRAM isolation, run_F7_check.py (cache hash verification, master vs ext4).

**How to run:** Python checks through the wrapper (`bash scripts/run_in_env.sh python tools/audit_env/check_imports.py`); shell checks directly in a login shell. `scripts/verify_env.sh` runs the read-only, GPU-free subset.

**Inputs:** Environment, caches, Ollama endpoint.

**Outputs:** Console output; run_F7_check.py writes `$INSIGHTEX_DATA/logs/env_audit/followup2/F7.txt`.

**Status:** Kept. check_packages.py initialises CUDA (torch, ctranslate2); verify_6e_sequential.py is a GPU check; verify_env_fix.sh creates cache dirs. These three are not part of verify_env.sh.

Standalone tool: it must not import from `backend/`.
