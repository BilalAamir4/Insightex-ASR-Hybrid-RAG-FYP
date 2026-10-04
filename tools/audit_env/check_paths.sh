#!/bin/bash
MASTER="${INSIGHTEX_MODEL_CACHE_MASTER:?run via scripts/run_in_env.sh or a login shell}"
E_ROOT="$(dirname "$(dirname "$MASTER")")"
paths=(
    "$MASTER"
    "$MASTER/huggingface"
    "$MASTER/pip"
    "$MASTER/torch"
    "$MASTER/paddlex"
    "$MASTER/paddle"
    "$(dirname "$MASTER")/LLMs"
    "$E_ROOT/LLMs"
    "$HOME/.paddlex"
    "$HOME/.cache/paddle"
)
for p in "${paths[@]}"; do
    if [ -L "$p" ]; then
        echo "SYMLINK: $p -> $(readlink -f "$p")"
    elif [ -d "$p" ]; then
        echo "DIR:     $p (exists, NOT symlink)"
    elif [ -e "$p" ]; then
        echo "EXISTS:  $p (exists, other)"
    else
        echo "MISSING: $p"
    fi
done
