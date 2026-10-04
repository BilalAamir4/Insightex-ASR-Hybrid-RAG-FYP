#!/usr/bin/env bash
PYTHON_BIN="/home/bilal_aamir/envs/insightex/bin/python"

echo "=== LD_LIBRARY_PATH CHECK ==="
echo "LD_LIBRARY_PATH: '$LD_LIBRARY_PATH'"
if [ -n "$LD_LIBRARY_PATH" ]; then
    echo "Entry count: $(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -v '^$' | wc -l)"
else
    echo "Entry count: 0"
fi
echo ""

echo "=== COMMAND 1: import ctranslate2; print(version) ==="
$PYTHON_BIN -c "import ctranslate2; print('ctranslate2 version:', ctranslate2.__version__)" 2> /tmp/cmd1.err
CMD1_STATUS=$?
echo "Exit code: $CMD1_STATUS"
if [ -s /tmp/cmd1.err ]; then
    echo "Stderr:"
    cat /tmp/cmd1.err
else
    echo "Stderr: (empty)"
fi
echo ""

echo "=== COMMAND 2: import ctranslate2; print(get_cuda_device_count()) ==="
$PYTHON_BIN -c "import ctranslate2; print('CUDA device count:', ctranslate2.get_cuda_device_count())" 2> /tmp/cmd2.err
CMD2_STATUS=$?
echo "Exit code: $CMD2_STATUS"
if [ -s /tmp/cmd2.err ]; then
    echo "Stderr:"
    cat /tmp/cmd2.err
else
    echo "Stderr: (empty)"
fi
echo ""

echo "=== COMMAND 3: WhisperModel CUDA load & transcribe ==="
$PYTHON_BIN /mnt/e/FYP/tools/env_audit/fail_whisper_test.py 2> /tmp/cmd3.err
CMD3_STATUS=$?
echo "Exit code: $CMD3_STATUS"
if [ -s /tmp/cmd3.err ]; then
    echo "Stderr:"
    cat /tmp/cmd3.err
else
    echo "Stderr: (empty)"
fi
echo ""
