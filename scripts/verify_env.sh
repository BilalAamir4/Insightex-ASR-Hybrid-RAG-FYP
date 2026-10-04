#!/bin/bash
# Read-only, GPU-free environment check: a plain list of calls to existing check scripts.
# Not included on purpose: check_packages.py (initialises CUDA), verify_6e_sequential.py (GPU),
# verify_env_fix.sh (creates directories), check_ps.sh and check_wsl_health.sh (system info only).
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
bash "$R/tools/audit_env/check_login_env.sh"
bash "$R/tools/audit_env/check_paths.sh"
bash "$R/tools/audit_env/check_shell_env.sh"
bash "$R/scripts/run_in_env.sh" python "$R/tools/audit_env/check_files_integrity.py"
bash "$R/scripts/run_in_env.sh" python "$R/tools/audit_env/check_env_vars.py"
bash "$R/scripts/run_in_env.sh" python "$R/tools/audit_env/check_imports.py"
bash "$R/scripts/run_in_env.sh" python "$R/tools/audit_env/check_av.py"
bash "$R/scripts/run_in_env.sh" python "$R/tools/audit_env/check_ollama_endpoint.py"
