#!/usr/bin/env python3
"""
Item 2: Honest load-time re-measurement.
Cold = after `echo 3 | sudo tee /proc/sys/vm/drop_caches`
Warm = immediate re-load (page cache hot).
Tests both /mnt/e/ (drvfs) and ~/cache/ (ext4) paths for Whisper + BGE-M3.
Each test runs in its own subprocess for VRAM isolation.
"""
import os
import sys
import time
import json
import subprocess

NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"

# Paths
WHISPER_CACHE_EXT4 = os.path.expanduser("~/cache/huggingface/hub")
WHISPER_CACHE_DRVFS = "/mnt/e/FYP/LLMs"  # if models are also here
BGE_CACHE_EXT4 = os.path.expanduser("~/cache/huggingface/hub")
BGE_CACHE_DRVFS = "/mnt/e/FYP/LLMs"

def get_vram_mb():
    try:
        out = subprocess.check_output(
            [NVIDIA_SMI, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

def drop_caches():
    """Drop page caches for cold measurement."""
    try:
        subprocess.run(
            ["sudo", "tee", "/proc/sys/vm/drop_caches"],
            input="3\n", text=True, capture_output=True, timeout=10
        )
        time.sleep(1)
        return True
    except Exception as e:
        print(f"  WARNING: Could not drop caches: {e}")
        return False

def load_whisper(model_size, cache_dir, compute_type="float16"):
    """Load a Whisper model and return load time."""
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(
        model_size,
        device="cuda",
        compute_type=compute_type,
        download_root=cache_dir,
    )
    load_time = time.time() - t0
    del model
    time.sleep(1)
    return load_time

def load_bge_m3(cache_dir):
    """Load BGE-M3 and return load time."""
    os.environ["HF_HOME"] = cache_dir if "huggingface" in cache_dir else os.path.join(cache_dir, "huggingface")
    from FlagEmbedding import BGEM3FlagModel
    t0 = time.time()
    model = BGEM3FlagModel(
        "BAAI/bge-m3",
        use_fp16=True,
        device="cuda",
    )
    load_time = time.time() - t0
    del model
    time.sleep(1)
    return load_time

def run_single_test(test_type, model_id, cache_dir, compute_type="float16"):
    """Run a single load test: cold then warm."""
    print(f"\n  --- {test_type}: {model_id} from {cache_dir} ---")

    # Check if the model actually exists at this cache_dir
    if not os.path.isdir(cache_dir):
        print(f"  SKIP: {cache_dir} does not exist")
        return None

    vram_before = get_vram_mb()
    print(f"  VRAM before: {vram_before} MiB")

    # Cold: drop caches first
    print(f"  Dropping page caches...")
    drop_caches()

    if test_type == "whisper":
        cold_time = load_whisper(model_id, cache_dir, compute_type)
        # Warm: load again without dropping caches
        warm_time = load_whisper(model_id, cache_dir, compute_type)
    elif test_type == "bge-m3":
        cold_time = load_bge_m3(cache_dir)
        warm_time = load_bge_m3(cache_dir)
    else:
        return None

    vram_after = get_vram_mb()
    result = {
        "test_type": test_type,
        "model_id": model_id,
        "cache_dir": cache_dir,
        "cold_s": round(cold_time, 2),
        "warm_s": round(warm_time, 2),
        "vram_before_mb": vram_before,
        "vram_after_mb": vram_after,
    }
    print(f"  Cold: {cold_time:.2f}s  Warm: {warm_time:.2f}s")
    print(f"  VRAM after: {vram_after} MiB")
    return result


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "--run-single":
        test_type = sys.argv[2]
        model_id = sys.argv[3]
        cache_dir = sys.argv[4]
        compute_type = sys.argv[5] if len(sys.argv) > 5 else "float16"
        result = run_single_test(test_type, model_id, cache_dir, compute_type)
        if result:
            print(f"\n__RESULT_JSON__:{json.dumps(result)}")
    else:
        # Parent: run all tests in subprocesses
        script = os.path.abspath(__file__)
        tests = []

        # Whisper medium and large-v3 from ext4
        tests.append(("whisper", "medium", WHISPER_CACHE_EXT4, "float16"))
        tests.append(("whisper", "large-v3", WHISPER_CACHE_EXT4, "float16"))

        # BGE-M3 from ext4
        tests.append(("bge-m3", "BAAI/bge-m3", BGE_CACHE_EXT4, ""))

        # Check if drvfs paths exist and have models
        if os.path.isdir(WHISPER_CACHE_DRVFS):
            tests.append(("whisper", "medium", WHISPER_CACHE_DRVFS, "float16"))
            tests.append(("whisper", "large-v3", WHISPER_CACHE_DRVFS, "float16"))

        results = []
        for test_type, model_id, cache_dir, ct in tests:
            print(f"\n>>> Subprocess: {test_type} / {model_id} / {cache_dir}")
            cmd = [sys.executable, script, "--run-single", test_type, model_id, cache_dir]
            if ct:
                cmd.append(ct)
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=600, env=os.environ.copy())
            print(proc.stdout)
            if proc.returncode != 0:
                print(f"STDERR: {proc.stderr[-500:]}")

            for line in proc.stdout.splitlines():
                if line.startswith("__RESULT_JSON__:"):
                    results.append(json.loads(line.split(":", 1)[1]))

            time.sleep(3)

        # Print summary table
        print(f"\n{'='*80}")
        print(f"  LOAD-TIME TABLE")
        print(f"{'='*80}")
        print(f"  {'Model':<20} {'Source':<12} {'Cold(s)':<10} {'Warm(s)':<10} {'Speedup':<10}")
        print(f"  {'-'*62}")
        for r in results:
            src = "ext4" if "/home/" in r["cache_dir"] else "drvfs"
            speedup = f"{r['cold_s']/r['warm_s']:.1f}x" if r["warm_s"] > 0 else "?"
            print(f"  {r['model_id']:<20} {src:<12} {r['cold_s']:<10} {r['warm_s']:<10} {speedup:<10}")

        print(f"\n__ALL_RESULTS__:{json.dumps(results)}")
