import os
import sys
import subprocess
import json
import glob
import hashlib
from pathlib import Path
from datetime import datetime

output_lines = []

def log(msg=""):
    print(msg)
    output_lines.append(str(msg))

def run_cmd(cmd, cwd=None):
    log(f"--- Running: {' '.join(cmd) if isinstance(cmd, list) else cmd} ---")
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=isinstance(cmd, str))
        log(f"Return Code: {res.returncode}")
        if res.stdout:
            log("STDOUT:")
            log(res.stdout.rstrip())
        if res.stderr:
            log("STDERR:")
            log(res.stderr.rstrip())
        return res
    except Exception as e:
        log(f"Exception running command: {e}")
        return None

log("=== TASK F1: OLLAMA MODEL IDENTITY CHANGE ===")

# Step a: ollama list, show, show --modelfile
log("\n--- Step a: ollama list, show, show --modelfile ---")
run_cmd(["ollama", "list"])
run_cmd(["ollama", "show", "qwen3.5:latest"])
run_cmd(["ollama", "show", "qwen3.5:latest", "--modelfile"])

# Step b: manifests and blobs
log("\n--- Step b: List E:\\FYP\\LLMs\\manifests and blobs ---")
manifest_dir = Path("E:/FYP/LLMs/manifests")
manifest_files = []
if manifest_dir.exists():
    for p in manifest_dir.rglob("*"):
        if p.is_file():
            stat = p.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            manifest_files.append((str(p), stat.st_size, mtime))
            log(f"Manifest File: {p} | Size: {stat.st_size} bytes | LastWriteTime: {mtime}")
else:
    log(f"Manifest dir {manifest_dir} does not exist!")

# Read manifests and collect referenced blob digests
referenced_digests = set()
for mpath, _, _ in manifest_files:
    try:
        with open(mpath, "rb") as f:
            raw_bytes = f.read()
            m_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            log(f"Manifest Full SHA256: {m_sha256} (12-char ID prefix: {m_sha256[:12]})")
            data = json.loads(raw_bytes.decode('utf-8'))
            log(f"Manifest JSON content of {mpath}:")
            log(json.dumps(data, indent=2))
            if "config" in data and "digest" in data["config"]:
                referenced_digests.add(data["config"]["digest"])
            if "layers" in data:
                for layer in data["layers"]:
                    if "digest" in layer:
                        referenced_digests.add(layer["digest"])
    except Exception as e:
        log(f"Error reading manifest {mpath}: {e}")

blob_dir = Path("E:/FYP/LLMs/blobs")
blob_files = []
if blob_dir.exists():
    for p in blob_dir.iterdir():
        if p.is_file():
            stat = p.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            blob_files.append((p.name, stat.st_size, mtime, stat.st_mtime))
    
    blob_files.sort(key=lambda x: x[3], reverse=True)
    log(f"\nTotal blob files found: {len(blob_files)}")
    log("Blobs sorted by LastWriteTime descending:")
    for name, size, mtime, _ in blob_files:
        is_ref = False
        for ref in referenced_digests:
            clean_ref = ref.split(":")[-1]
            if clean_ref in name:
                is_ref = True
                break
        status_str = "REFERENCED" if is_ref else "UNREFERENCED"
        log(f"Blob: {name} | Size: {size} bytes ({size/(1024**3):.4f} GiB) | LastWriteTime: {mtime} | Status: {status_str}")

    unreferenced = []
    for name, size, mtime, _ in blob_files:
        matched = False
        for ref in referenced_digests:
            clean_ref = ref.split(":")[-1]
            if clean_ref in name:
                matched = True
                break
        if not matched:
            unreferenced.append((name, size, mtime))
    log(f"\nUnreferenced blobs count: {len(unreferenced)}")
    for u in unreferenced:
        log(f"  Unreferenced Blob: {u[0]} | Size: {u[1]} bytes | LastWriteTime: {u[2]}")
else:
    log(f"Blob dir {blob_dir} does not exist!")

# Step c: Search Ollama logs
log("\n--- Step c: Search Ollama logs ---")
log_dirs = [
    Path("C:/Users/Bilal Aamir/.ollama/logs"),
    Path("C:/Users/Bilal Aamir/AppData/Local/Ollama")
]

search_terms = ["pulling", "pull", "create", "writing manifest", "verifying sha256", "success", "delete", "6488c96fa5fa", "b896b1b46a78"]
all_log_files = []
for ld in log_dirs:
    if ld.exists():
        for p in ld.rglob("*"):
            if p.is_file() and (p.suffix in [".log", ".txt"] or "log" in p.name.lower()):
                if p not in all_log_files:
                    all_log_files.append(p)

log("Log files searched:")
for lf in all_log_files:
    log(f"  {lf} | Size: {lf.stat().st_size} bytes")

log("\nMatches in log files (excluding installer logs and github pull request URLs):")
relevant_matches = 0
for lf in all_log_files:
    try:
        with open(lf, "r", encoding="utf-8", errors="ignore") as f:
            for lno, line in enumerate(f, 1):
                line_lower = line.lower()
                for term in search_terms:
                    if term.lower() in line_lower:
                        # Exclude generic installer logs or github pull request URLs if looking for ollama operations
                        if "github.com" in line_lower:
                            continue
                        if "upgrade.log" in str(lf).lower() and ("shortcut" in line_lower or "icon" in line_lower or "install" in line_lower):
                            continue
                        log(f"{lf}:{lno}: [{term}] {line.strip()}")
                        relevant_matches += 1
                        break
    except Exception as e:
        log(f"Error reading log file {lf}: {e}")

if relevant_matches == 0:
    log("no relevant matches in the files searched")

# Step d: Search own scripts and command outputs for ollama pull/create/cp/rm
log("\n--- Step d: Check scripts and results for pull/create/cp/rm ---")
script_patterns = [
    "E:/FYP/tools/env_audit/*.py",
    "E:/FYP/tools/env_audit/*.sh",
    "E:/FYP/tools/env_audit/*.ps1",
    "E:/FYP/tools/env_audit/results/followup/*.txt"
]

target_patterns = [
    "ollama pull", "ollama create", "ollama cp", "ollama rm",
    "/api/pull", "/api/create", "/api/copy", "/api/delete"
]

script_files = []
for pat in script_patterns:
    for f in glob.glob(pat):
        # Exclude this audit script itself
        if "run_F1_audit.py" not in f:
            script_files.append(f)

script_matches = []
for sf in script_files:
    try:
        with open(sf, "r", encoding="utf-8", errors="ignore") as f:
            for lno, line in enumerate(f, 1):
                for tp in target_patterns:
                    if tp in line.lower():
                        script_matches.append((sf, lno, tp, line.strip()))
    except Exception as e:
        log(f"Error reading {sf}: {e}")

if script_matches:
    log(f"Found {len(script_matches)} matches in scripts/results:")
    for sm in script_matches:
        log(f"{sm[0]}:{sm[1]}: [{sm[2]}] {sm[3]}")
else:
    log("no matches")

# Save all raw output to followup2/F1.txt
out_path = Path("E:/FYP/tools/env_audit/results/followup2/F1.txt")
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")

log(f"\nRaw output saved to {out_path}")
