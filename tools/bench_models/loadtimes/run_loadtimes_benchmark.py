#!/usr/bin/env python3
"""
Orchestrator for load-time benchmarking.
Runs on Windows host (or WSL) and invokes WSL commands:
- Drops WSL cache using `wsl -u root -e bash -c "sync; echo 3 > /proc/sys/vm/drop_caches"`
- Runs worker in ~/envs/insightex
- Measures both ext4 (~/cache/huggingface/hub) and drvfs ($INSIGHTEX_MODEL_CACHE_MASTER/huggingface/hub)
"""
import subprocess
import json
import time
import os

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loadtimes_results.json")

TESTS = [
    # (type, name, path_label, cache_path, compute_type)
    # cache paths are expanded by the WSL shell after the env script is sourced (see run_test)
    ("whisper", "medium", "ext4 (~/cache)", "$HOME/cache/huggingface/hub", "float16"),
    ("whisper", "medium", "drvfs (cache master)", "$INSIGHTEX_MODEL_CACHE_MASTER/huggingface/hub", "float16"),
    ("whisper", "large-v3", "ext4 (~/cache)", "$HOME/cache/huggingface/hub", "float16"),
    ("whisper", "large-v3", "drvfs (cache master)", "$INSIGHTEX_MODEL_CACHE_MASTER/huggingface/hub", "float16"),
    ("bge-m3", "BAAI/bge-m3", "ext4 (~/cache)", "$HOME/cache/huggingface/hub", ""),
    ("bge-m3", "BAAI/bge-m3", "drvfs (cache master)", "$INSIGHTEX_MODEL_CACHE_MASTER/huggingface/hub", ""),
]

def drop_wsl_caches():
    print("  [CACHE] Dropping WSL page caches (wsl -u root)...")
    subprocess.run(["wsl", "-u", "root", "-e", "bash", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"], check=True)
    time.sleep(1)

def run_test(mtype, mname, plabel, cpath, ctype):
    print(f"\n{'='*70}")
    print(f"BENCHMARK: {mtype} - {mname} from {plabel}")
    print(f"{'='*70}")

    drop_wsl_caches()

    wsl_cmd = (
        f'source "$HOME/insightex/env/insightex_env.sh" && '
        f'bash "$INSIGHTEX_HOME/scripts/run_in_env.sh" '
        f'python3 "$INSIGHTEX_HOME/tools/bench_models/loadtimes/load_single_model.py" {mtype} {mname} {cpath} {ctype}'
    )

    t0 = time.time()
    proc = subprocess.run(
        ["wsl", "-d", "Ubuntu-24.04", "--", "bash", "-c", wsl_cmd],
        capture_output=True,
        text=True,
        timeout=300
    )
    total_time = time.time() - t0

    result = None
    for line in proc.stdout.splitlines():
        if line.startswith("__RESULT__:"):
            result = json.loads(line[len("__RESULT__:"):])
            break

    if result:
        result["location"] = plabel
        print(f"  Cold Load: {result['cold_s']}s")
        print(f"  Warm Load: {result['warm_s']}s")
        speedup = round(result['cold_s'] / result['warm_s'], 1) if result['warm_s'] > 0 else 0
        print(f"  Speedup:   {speedup}x")
        print(f"  Peak VRAM: {result['vram_peak_mb']} MiB")
        return result
    else:
        print(f"  ERROR running test: exit={proc.returncode}")
        print("  STDOUT:", proc.stdout[:300])
        print("  STDERR:", proc.stderr[:300])
        return None

if __name__ == "__main__":
    results = []
    for mtype, mname, plabel, cpath, ctype in TESTS:
        r = run_test(mtype, mname, plabel, cpath, ctype)
        if r:
            results.append(r)
        time.sleep(2)

    print("\n" + "="*70)
    print("FINAL LOAD-TIME TABLE")
    print("="*70)
    print(f"{'Model':<22} {'Location':<24} {'Cold (s)':<10} {'Warm (s)':<10} {'Speedup':<10} {'Peak VRAM'}")
    print("-" * 88)
    for r in results:
        m = r['model']
        loc = r['location']
        cold = f"{r['cold_s']}s"
        warm = f"{r['warm_s']}s"
        sp = f"{round(r['cold_s']/r['warm_s'], 1)}x" if r['warm_s'] > 0 else "-"
        vram = f"{r['vram_peak_mb']} MiB"
        print(f"{m:<22} {loc:<24} {cold:<10} {warm:<10} {sp:<10} {vram}")

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {RESULTS_FILE}")
