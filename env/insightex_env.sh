#!/usr/bin/env bash
# Insightex Environment Configuration for WSL2 Ubuntu-24.04

# Guard: only run once per shell to avoid duplicating LD_LIBRARY_PATH
[ -n "$_INSIGHTEX_ENV_LOADED" ] && return 0 2>/dev/null || true
export _INSIGHTEX_ENV_LOADED=1

export INSIGHTEX_HOME="$HOME/insightex"
export INSIGHTEX_DATA="$HOME/insightex-data"
export INSIGHTEX_MODEL_CACHE_MASTER="/mnt/e/FYP/cache"
export HF_HOME="$HOME/cache/huggingface"
export HF_HUB_OFFLINE=1
export OLLAMA_BASE_URL="http://localhost:11434"
export PIP_CACHE_DIR="$HOME/cache/pip"
export TORCH_HOME="$HOME/cache/torch"

# NVIDIA CUDA/cuDNN dynamic library paths for ctranslate2 & torch
NVIDIA_SITE="$HOME/envs/insightex/lib/python3.12/site-packages/nvidia"
NVIDIA_LD_DIRS=$(find "$NVIDIA_SITE" -mindepth 2 -maxdepth 2 -type d -name "lib" 2>/dev/null | tr '\n' ':')

export LD_LIBRARY_PATH="/usr/lib/wsl/lib:${NVIDIA_LD_DIRS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
