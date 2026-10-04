#!/bin/bash
echo "=== DMESG TAIL ==="
dmesg | tail -n 30
echo "=== DF -H / ==="
df -h /
