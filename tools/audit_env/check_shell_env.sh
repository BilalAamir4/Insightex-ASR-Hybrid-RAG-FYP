#!/bin/bash
# Item 4: Shell environment transparency
echo "=== ENVIRONMENT VARIABLES ==="
echo "PIP_CACHE_DIR=$PIP_CACHE_DIR"
echo "TORCH_HOME=$TORCH_HOME"
echo "HF_HOME=$HF_HOME"
echo "HF_HUB_OFFLINE=$HF_HUB_OFFLINE"
echo "OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
echo "INSIGHTEX_HOME=$INSIGHTEX_HOME"
echo "INSIGHTEX_DATA=$INSIGHTEX_DATA"
echo "INSIGHTEX_MODEL_CACHE_MASTER=$INSIGHTEX_MODEL_CACHE_MASTER"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
echo "VIRTUAL_ENV=$VIRTUAL_ENV"
echo "PATH (first 200)=${PATH:0:200}"
echo ""
echo "=== INSIGHTEX_ENV.SH ==="
cat "$INSIGHTEX_HOME/env/insightex_env.sh"
echo ""
echo "=== .BASHRC DIFF FROM STOCK ==="
echo "Lines added to stock bashrc:"
# The stock Ubuntu bashrc is well-known; just show what was added
head -1 ~/.bashrc
tail -1 ~/.bashrc
echo ""
echo "=== .WSLCONFIG (if exists) ==="
if [ -f /mnt/c/Users/Bilal\ Aamir/.wslconfig ]; then
    cat "/mnt/c/Users/Bilal Aamir/.wslconfig"
else
    echo "(does not exist)"
fi
echo ""
echo "=== .WSLCONFIG.BAK (if exists) ==="
if [ -f /mnt/c/Users/Bilal\ Aamir/.wslconfig.bak ]; then
    cat "/mnt/c/Users/Bilal Aamir/.wslconfig.bak"
else
    echo "(does not exist)"
fi
