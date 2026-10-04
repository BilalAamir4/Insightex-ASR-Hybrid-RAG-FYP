#!/bin/bash
# Verify env after insightex_env.sh fix
source /mnt/e/FYP/env/insightex_env.sh
echo "PIP_CACHE_DIR=$PIP_CACHE_DIR"
echo "TORCH_HOME=$TORCH_HOME"
echo "HF_HOME=$HF_HOME"
echo "INSIGHTEX_ROOT=$INSIGHTEX_ROOT"
echo "_INSIGHTEX_ENV_LOADED=$_INSIGHTEX_ENV_LOADED"
echo "LD_LIBRARY_PATH length: ${#LD_LIBRARY_PATH}"

# Source again to test idempotency
source /mnt/e/FYP/env/insightex_env.sh
echo "LD_LIBRARY_PATH length after 2nd source: ${#LD_LIBRARY_PATH}"

# Ensure cache dirs exist
mkdir -p ~/cache/pip ~/cache/torch
ls -ld ~/cache/pip ~/cache/torch
