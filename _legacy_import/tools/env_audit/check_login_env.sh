#!/bin/bash
echo "HF_HOME=$HF_HOME"
echo "HF_HUB_OFFLINE=$HF_HUB_OFFLINE"
echo "PIP_CACHE_DIR=$PIP_CACHE_DIR"
echo "TORCH_HOME=$TORCH_HOME"
echo "OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
if [ -n "$LD_LIBRARY_PATH" ]; then
    NUM_LD=$(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -v '^$' | wc -l)
else
    NUM_LD=0
fi
echo "LD_LIBRARY_PATH entries count=$NUM_LD"
