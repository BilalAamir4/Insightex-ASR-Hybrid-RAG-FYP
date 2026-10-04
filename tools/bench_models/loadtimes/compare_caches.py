import os
from pathlib import Path

master_base = Path("/mnt/e/FYP/cache/huggingface/hub")
runtime_base = Path("/home/bilal_aamir/cache/huggingface/hub")

models = [
    "models--BAAI--bge-m3",
    "models--Systran--faster-whisper-medium",
    "models--Systran--faster-whisper-large-v3"
]

def get_dir_file_sizes(dir_path):
    # Resolves symlinks in snapshots
    result = {}
    if not dir_path.exists():
        return result
    for root, _, files in os.walk(dir_path):
        for f in files:
            full_path = Path(root) / f
            # resolve real path if symlink
            try:
                rel = full_path.relative_to(dir_path)
                stat = full_path.stat()
                result[str(rel)] = stat.st_size
            except Exception as e:
                result[str(full_path)] = -1
    return result

print("=== COMPARING MASTER (E:) VS RUNTIME (~/cache) ===")
print(f"Master dir: {master_base}")
print(f"Runtime dir: {runtime_base}")

for m in models:
    print(f"\n--- Model: {m} ---")
    m_dir = master_base / m
    r_dir = runtime_base / m
    print(f"Master exists: {m_dir.exists()} | Runtime exists: {r_dir.exists()}")
    
    m_files = get_dir_file_sizes(m_dir)
    r_files = get_dir_file_sizes(r_dir)
    
    m_total = sum(v for v in m_files.values() if v > 0)
    r_total = sum(v for v in r_files.values() if v > 0)
    
    print(f"Master file count: {len(m_files)}, total size: {m_total:,} bytes ({m_total / (1024**2):.2f} MB)")
    print(f"Runtime file count: {len(r_files)}, total size: {r_total:,} bytes ({r_total / (1024**2):.2f} MB)")
    
    diff_count = 0
    all_keys = sorted(set(m_files.keys()).union(set(r_files.keys())))
    for k in all_keys:
        s_m = m_files.get(k)
        s_r = r_files.get(k)
        if s_m != s_r:
            print(f"  DIFF: {k} (Master: {s_m}, Runtime: {s_r})")
            diff_count += 1
            if diff_count > 10:
                print("  ... more diffs truncated")
                break
    if diff_count == 0:
        print("  MATCH: All files and sizes match perfectly!")
