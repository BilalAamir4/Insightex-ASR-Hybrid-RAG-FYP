#!/bin/bash
paths=(
    "/mnt/e/FYP/cache"
    "/mnt/e/FYP/cache/huggingface"
    "/mnt/e/FYP/cache/pip"
    "/mnt/e/FYP/cache/torch"
    "/mnt/e/FYP/cache/paddlex"
    "/mnt/e/FYP/cache/paddle"
    "/mnt/e/FYP/LLMs"
    "/mnt/e/LLMs"
    "/home/bilal_aamir/.paddlex"
    "/home/bilal_aamir/.cache/paddle"
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
