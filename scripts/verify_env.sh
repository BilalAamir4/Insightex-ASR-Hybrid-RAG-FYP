#!/bin/bash
# M0 exit: the single verification entry point is tools/verify_env.py; this is only a wrapper.
# (The older tools/audit_env/check_* scripts are diagnostics and are not part of this check.)
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
exec bash "$R/scripts/run_in_env.sh" python "$R/tools/verify_env.py" "$@"
