import os
import sys
import time
from pathlib import Path

now = time.time()
one_day_ago = now - 24 * 3600

def check_file(path_str):
    p = Path(path_str).expanduser()
    if not p.exists():
        print(f"FILE NOT FOUND: {path_str}")
        return
    stat = p.stat()
    size = stat.st_size
    mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
    is_recent = stat.st_mtime >= one_day_ago
    
    # Check emptiness and ending
    status = "OK"
    last_line = ""
    if size == 0:
        status = "EMPTY"
    else:
        try:
            with open(p, "rb") as f:
                content = f.read()
            if not content.endswith(b"\n") and not content.endswith(b"\r\n"):
                status = "NO_TRAILING_NEWLINE (check truncation)"
            # check last 200 chars as text
            text = content.decode('utf-8', errors='replace')
            lines = [l for l in text.splitlines() if l.strip()]
            if lines:
                last_line = lines[-1][:80]
        except Exception as e:
            status = f"READ_ERROR: {e}"
            
    print(f"{path_str} | Size: {size} bytes | Mtime: {mtime} | Recent(<24h): {is_recent} | Status: {status}")
    if last_line:
        print(f"   Last non-empty line: {last_line}")

print("=== CHECKING tools/audit_env/ ===")
audit_dir = Path(os.environ["INSIGHTEX_HOME"]) / "tools/audit_env"
for f in sorted(audit_dir.iterdir()):
    if f.is_file():
        check_file(str(f))

print("\n=== CHECKING SPECIFIC PROJECT & HOME FILES ===")
specific_files = [
    os.environ["INSIGHTEX_HOME"] + "/env/insightex_env.sh",
    os.environ["INSIGHTEX_HOME"] + "/requirements.lock.txt",
    os.environ["INSIGHTEX_HOME"] + "/docs/ENVIRONMENT.md",
    "~/.bashrc",
    "~/.profile",
    "~/.bash_profile",
    "~/.bash_login"
]
for sf in specific_files:
    check_file(sf)
