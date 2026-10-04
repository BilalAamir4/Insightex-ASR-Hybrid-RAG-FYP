#!/usr/bin/env python3
"""
TASK T5: Re-verify or relabel carried-over claims.
Collects fresh raw outputs for:
- Ollama version
- Windows FFmpeg version
- GPU driver and CUDA version
- Ollama loopback binding (netstat & Get-NetTCPConnection)
Saves to E:\FYP\tools\env_audit\results\followup\T5.txt
"""
import subprocess
from pathlib import Path

OUT_FILE = Path(r"E:\FYP\tools\env_audit\results\followup\T5.txt")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

out_lines = []
def log(msg=""):
    print(msg, flush=True)
    out_lines.append(msg)

log("======================================================================")
log("TASK T5: RE-VERIFICATION OF CARRIED-OVER CLAIMS")
log("======================================================================\n")

# 1. Ollama version
log("=== 1. Ollama Version ===")
cmd_ollama = ["ollama", "--version"]
res_ollama = subprocess.run(cmd_ollama, capture_output=True, text=True)
log(f"Command: {' '.join(cmd_ollama)}")
log(f"STDOUT: {res_ollama.stdout.strip()}")
if res_ollama.stderr: log(f"STDERR: {res_ollama.stderr.strip()}")
log(f"Exit code: {res_ollama.returncode}\n")

# 2. Windows FFmpeg version
log("=== 2. Windows FFmpeg Version ===")
ffmpeg_exe = r"E:\Uni Softwares\FFMPEG\bin\ffmpeg.exe"
cmd_ffmpeg = [ffmpeg_exe, "-version"]
try:
    res_ffmpeg = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)
    log(f"Command: {ffmpeg_exe} -version")
    log("STDOUT (first 5 lines):")
    for l in res_ffmpeg.stdout.splitlines()[:5]:
        log(f"  {l}")
    log(f"Exit code: {res_ffmpeg.returncode}\n")
except Exception as e:
    log(f"Error running Windows FFmpeg: {e}\n")

# 3. GPU driver and CUDA version (nvidia-smi header)
log("=== 3. GPU Driver and CUDA Version (nvidia-smi) ===")
cmd_smi = ["nvidia-smi"]
res_smi = subprocess.run(cmd_smi, capture_output=True, text=True)
log("STDOUT (header):")
for l in res_smi.stdout.splitlines()[:10]:
    log(f"  {l}")
log(f"Exit code: {res_smi.returncode}\n")

# 4. Ollama loopback binding
log("=== 4. Ollama Loopback Binding ===")
# netstat
cmd_netstat = ["powershell.exe", "-Command", "netstat -ano | findstr 11434"]
res_netstat = subprocess.run(cmd_netstat, capture_output=True, text=True)
log("netstat -ano | findstr 11434:")
log(res_netstat.stdout.strip())

# Get-NetTCPConnection
cmd_tcp = ["powershell.exe", "-Command", "Get-NetTCPConnection -LocalPort 11434 | Format-List LocalAddress,LocalPort,State,OwningProcess"]
res_tcp = subprocess.run(cmd_tcp, capture_output=True, text=True)
log("\nGet-NetTCPConnection -LocalPort 11434:")
log(res_tcp.stdout.strip())
log(f"Exit code: {res_tcp.returncode}")

# Confirmation
local_addr_ok = "127.0.0.1" in res_tcp.stdout and "0.0.0.0" not in res_tcp.stdout and "::" not in res_tcp.stdout
log(f"\nCONFIRMATION: LocalAddress is 127.0.0.1 and not 0.0.0.0 or ::: {local_addr_ok}")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines) + "\n")

log(f"\nSaved raw output to {OUT_FILE}")
