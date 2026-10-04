#!/bin/bash
source "$(dirname "$(readlink -f "$0")")/../env/insightex_env.sh"
source "$HOME/envs/insightex/bin/activate"
exec "$@"
