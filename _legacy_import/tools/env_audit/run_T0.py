import os
import subprocess
import sys
from pathlib import Path

out_dir = Path(r"E:\FYP\tools\env_audit\results\followup")
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / "T0.txt"

commands = [
    ("wsl -l -v", ["wsl", "-l", "-v"]),
    ("ollama list", ["ollama", "list"]),
    ("ollama ps", ["ollama", "ps"]),
    ("nvidia-smi (Windows)", ["nvidia-smi"]),
    ("nvidia-smi (WSL)", ["wsl", "-d", "Ubuntu-24.04", "/usr/lib/wsl/lib/nvidia-smi"]),
]

output_lines = []
for name, cmd in commands:
    output_lines.append(f"=== {name} ===")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output_lines.append(res.stdout)
        if res.stderr:
            output_lines.append("--- STDERR ---")
            output_lines.append(res.stderr)
        output_lines.append(f"[Exit code: {res.returncode}]\n")
    except Exception as e:
        output_lines.append(f"ERROR: {e}\n")

full_output = "\n".join(output_lines)
with open(out_file, "w", encoding="utf-8") as f:
    f.write(full_output)

print(full_output)
