#!/usr/bin/env python3
"""
Worker script to measure cold and warm load time of a single model.
Runs inside WSL Ubuntu-24.04 venv ~/envs/insightex.
"""
import sys
import os
import time
import json
import subprocess

NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"

def get_vram_mb():
    try:
        out = subprocess.check_output(
            [NVIDIA_SMI, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

def measure_whisper(model_size, cache_dir, compute_type="float16"):
    from faster_whisper import WhisperModel
    # First load (cold if cache was just dropped)
    vram_before = get_vram_mb()
    t0 = time.time()
    m1 = WhisperModel(
        model_size,
        device="cuda",
        compute_type=compute_type,
        download_root=cache_dir,
    )
    cold_time = time.time() - t0
    vram_peak = get_vram_mb()
    del m1
    time.sleep(1)

    # Second load (warm - page cache hot)
    t1 = time.time()
    m2 = WhisperModel(
        model_size,
        device="cuda",
        compute_type=compute_type,
        download_root=cache_dir,
    )
    warm_time = time.time() - t1
    del m2
    time.sleep(1)
    vram_after = get_vram_mb()

    return {
        "model": f"whisper-{model_size}",
        "cache_dir": cache_dir,
        "compute_type": compute_type,
        "cold_s": round(cold_time, 2),
        "warm_s": round(warm_time, 2),
        "vram_before_mb": vram_before,
        "vram_peak_mb": vram_peak,
        "vram_after_mb": vram_after,
    }

def measure_bge(cache_dir):
    # Set HF_HOME to parent of hub
    parent = os.path.dirname(cache_dir) if cache_dir.endswith("/hub") or cache_dir.endswith("\\hub") else cache_dir
    os.environ["HF_HOME"] = parent
    os.environ["HF_HUB_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer

    vram_before = get_vram_mb()
    t0 = time.time()
    m1 = SentenceTransformer(
        "BAAI/bge-m3",
        device="cuda",
    )
    cold_time = time.time() - t0
    vram_peak = get_vram_mb()
    del m1
    time.sleep(1)

    t1 = time.time()
    m2 = SentenceTransformer(
        "BAAI/bge-m3",
        device="cuda",
    )
    warm_time = time.time() - t1
    del m2
    time.sleep(1)
    vram_after = get_vram_mb()

    return {
        "model": "bge-m3",
        "cache_dir": cache_dir,
        "cold_s": round(cold_time, 2),
        "warm_s": round(warm_time, 2),
        "vram_before_mb": vram_before,
        "vram_peak_mb": vram_peak,
        "vram_after_mb": vram_after,
    }

if __name__ == "__main__":
    model_type = sys.argv[1] # "whisper" or "bge-m3"
    model_name = sys.argv[2] # "medium", "large-v3", or "BAAI/bge-m3"
    cache_dir = sys.argv[3]
    compute_type = sys.argv[4] if len(sys.argv) > 4 else "float16"

    if model_type == "whisper":
        res = measure_whisper(model_name, cache_dir, compute_type)
    elif model_type == "bge-m3":
        res = measure_bge(cache_dir)
    else:
        sys.exit(1)

    print("__RESULT__:" + json.dumps(res))
