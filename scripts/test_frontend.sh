#!/bin/bash
# Frontend unit tests, run with the Deno installed in the venv (no Node, no network).
#   bash scripts/test_frontend.sh
source "$(dirname "$(readlink -f "$0")")/../env/insightex_env.sh"
source "$HOME/envs/insightex/bin/activate"
cd "$(dirname "$(readlink -f "$0")")/../frontend" || exit 1
exec deno test --no-check --no-lock
