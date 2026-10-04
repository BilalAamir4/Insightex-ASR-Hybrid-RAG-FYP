import sys
import subprocess
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_TXT = Path("E:/FYP/tools/env_audit/results/followup2/F6.txt")

output_lines = []

def log(msg=""):
    print(msg, flush=True)
    output_lines.append(str(msg))

def get_vram_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

def run_cmd(cmd):
    log(f"--- Running: {' '.join(cmd)} ---")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(f"Return Code: {res.returncode}")
    if res.stdout:
        log("STDOUT:")
        log(res.stdout.rstrip())
    if res.stderr:
        log("STDERR:")
        log(res.stderr.rstrip())
    return res

log("=== TASK F6: LAUNCHER FAILURE MODE, EXACT COMMAND AND RAW ERROR ===")
idle_before = get_vram_mb()
log(f"Idle VRAM before tests: {idle_before} MiB\n")

# Mode 1: Without wrapper (plain non-login, non-interactive bash)
log("======================================================================")
log("MODE 1: WITHOUT WRAPPER (plain non-login, non-interactive shell)")
log("Command: wsl -d Ubuntu-24.04 bash /mnt/e/FYP/tools/env_audit/fail_mode_test.sh")
log("======================================================================")
run_cmd(["wsl", "-d", "Ubuntu-24.04", "bash", "/mnt/e/FYP/tools/env_audit/fail_mode_test.sh"])

# Mode 2: With wrapper (run_in_env.sh)
log("\n======================================================================")
log("MODE 2: WITH WRAPPER (run_in_env.sh)")
log("Command: wsl -d Ubuntu-24.04 bash /mnt/e/FYP/tools/env_audit/run_in_env.sh bash /mnt/e/FYP/tools/env_audit/fail_mode_test.sh")
log("======================================================================")
run_cmd(["wsl", "-d", "Ubuntu-24.04", "bash", "/mnt/e/FYP/tools/env_audit/run_in_env.sh", "bash", "/mnt/e/FYP/tools/env_audit/fail_mode_test.sh"])

# Additional test: plain system python3 check
log("\n======================================================================")
log("ADDITIONAL TEST: System python3 (/usr/bin/python3) without wrapper")
log("Command: wsl -d Ubuntu-24.04 python3 -c 'import ctranslate2'")
log("======================================================================")
run_cmd(["wsl", "-d", "Ubuntu-24.04", "python3", "-c", "import ctranslate2"])

# Also check system python3 path vs venv python path
log("\n--- Checking Python Binaries in WSL ---")
run_cmd(["wsl", "-d", "Ubuntu-24.04", "which", "python3"])
run_cmd(["wsl", "-d", "Ubuntu-24.04", "bash", "/mnt/e/FYP/tools/env_audit/run_in_env.sh", "which", "python"])

time.sleep(2)
vram_after = get_vram_mb()
log(f"\nPost-test VRAM: {vram_after} MiB (Delta from initial idle: {vram_after - idle_before} MiB)")

OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")
log(f"\nRaw output saved to {OUT_TXT}")
