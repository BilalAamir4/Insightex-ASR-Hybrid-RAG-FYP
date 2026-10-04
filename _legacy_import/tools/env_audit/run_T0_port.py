import subprocess
from pathlib import Path

out_file = Path(r"E:\FYP\tools\env_audit\results\followup\T0.txt")

ps_script = """
Get-NetTCPConnection -LocalPort 11434 -ErrorAction SilentlyContinue | Format-List LocalAddress,LocalPort,State,OwningProcess
"""

res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
with open(out_file, "a", encoding="utf-8") as f:
    f.write("=== Ollama TCP Connection ===\n")
    f.write(res.stdout)
    f.write(f"\n[Exit code: {res.returncode}]\n")

print(res.stdout)
