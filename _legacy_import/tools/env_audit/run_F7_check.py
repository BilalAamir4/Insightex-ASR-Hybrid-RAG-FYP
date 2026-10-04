import hashlib
import json
from pathlib import Path

OUT_TXT = Path("E:/FYP/tools/env_audit/results/followup2/F7.txt")

output_lines = []

def log(msg=""):
    print(msg, flush=True)
    output_lines.append(str(msg))

log("=== TASK F7: RELABEL CARRIED-OVER AND UNSUPPORTED ITEMS ===")

# Step b: LFS blob filename vs SHA256
log("\n--- Step b: LFS Blob Filename vs Computed SHA256 Check ---")
import os
if os.path.exists("/mnt/e/FYP/cache/huggingface/hub"):
    master_cache = Path("/mnt/e/FYP/cache/huggingface/hub")
    OUT_TXT = Path("/mnt/e/FYP/tools/env_audit/results/followup2/F7.txt")
else:
    master_cache = Path("E:/FYP/cache/huggingface/hub")
    OUT_TXT = Path("E:/FYP/tools/env_audit/results/followup2/F7.txt")
models = [
    "models--BAAI--bge-m3",
    "models--Systran--faster-whisper-medium",
    "models--Systran--faster-whisper-large-v3"
]

for m in models:
    log(f"\nModel: {m}")
    blobs_dir = master_cache / m / "blobs"
    if not blobs_dir.exists():
        log(f"  Blobs dir {blobs_dir} not found!")
        continue
    
    for f in sorted(blobs_dir.iterdir()):
        if not f.is_file(): continue
        fname = f.name
        fsize = f.stat().st_size
        
        # Calculate SHA256
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            while chunk := fh.read(1024*1024):
                h.update(chunk)
        calc_sha256 = h.hexdigest()
        
        # Is filename a 64-char sha256?
        if len(fname) == 64 and all(c in '0123456789abcdef' for c in fname.lower()):
            is_match = (calc_sha256.lower() == fname.lower())
            status = "MATCH (LFS blob)" if is_match else "MISMATCH (LFS blob)"
        elif len(fname) == 40 and all(c in '0123456789abcdef' for c in fname.lower()):
            status = "not an LFS blob (git sha1 name)"
        else:
            status = "non-standard blob name"
            
        log(f"  File: {fname[:16]}... ({fsize:>10} bytes) | Status: {status} | Computed: {calc_sha256[:16]}...")

# Step b part 2: Compute ratios for earlier 2919 / 5895 MB
log("\n--- Step b (part 2): Size Ratio Computations ---")
earlier_medium_mb = 2919.0
earlier_large_mb = 5895.0

real_medium_bytes = 1530305671
real_large_bytes = 3091691489

# In decimal MB (1 MB = 1,000,000 bytes)
real_medium_dec_mb = real_medium_bytes / 1e6
real_large_dec_mb = real_large_bytes / 1e6

# In binary MiB (1 MiB = 1,048,576 bytes)
real_medium_bin_mb = real_medium_bytes / (1024 * 1024)
real_large_bin_mb = real_large_bytes / (1024 * 1024)

ratio_med_dec = earlier_medium_mb / real_medium_dec_mb
ratio_large_dec = earlier_large_mb / real_large_dec_mb

ratio_med_bin = earlier_medium_mb / real_medium_bin_mb
ratio_large_bin = earlier_large_mb / real_large_bin_mb

log(f"Medium Model:")
log(f"  Earlier reported: {earlier_medium_mb} MB")
log(f"  Real size: {real_medium_bytes} bytes ({real_medium_dec_mb:.2f} decimal MB, {real_medium_bin_mb:.2f} binary MiB)")
log(f"  Ratio (earlier / decimal MB): {earlier_medium_mb} / {real_medium_dec_mb:.2f} = {ratio_med_dec:.4f}x (roughly {ratio_med_dec:.2f}x)")
log(f"  Ratio (earlier / binary MiB):  {earlier_medium_mb} / {real_medium_bin_mb:.2f} = {ratio_med_bin:.4f}x (roughly {ratio_med_bin:.2f}x)")

log(f"\nLarge-v3 Model:")
log(f"  Earlier reported: {earlier_large_mb} MB")
log(f"  Real size: {real_large_bytes} bytes ({real_large_dec_mb:.2f} decimal MB, {real_large_bin_mb:.2f} binary MiB)")
log(f"  Ratio (earlier / decimal MB): {earlier_large_mb} / {real_large_dec_mb:.2f} = {ratio_large_dec:.4f}x (roughly {ratio_large_dec:.2f}x)")
log(f"  Ratio (earlier / binary MiB):  {earlier_large_mb} / {real_large_bin_mb:.2f} = {ratio_large_bin:.4f}x (roughly {ratio_large_bin:.2f}x)")

OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")
log(f"\nRaw output written to {OUT_TXT}")
