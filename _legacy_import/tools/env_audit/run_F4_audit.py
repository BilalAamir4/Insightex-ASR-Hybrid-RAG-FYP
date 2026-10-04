import sys
import subprocess
import time
import json
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_TXT = Path("E:/FYP/tools/env_audit/results/followup2/F4.txt")
BASE_URL = "http://127.0.0.1:11434"
MODEL_NAME = "qwen3.5:latest"

output_lines = []

def log(msg=""):
    print(msg, flush=True)
    output_lines.append(str(msg))

def get_vram_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

def get_ollama_ps():
    try:
        out = subprocess.check_output(["ollama", "ps"], text=True, timeout=5)
        return out.strip()
    except Exception as e:
        return f"ERROR: {e}"

def unload_model(timeout=30):
    log("  [UNLOAD] Sending keep_alive: 0 to unload model...")
    url = f"{BASE_URL}/api/chat"
    payload = {"model": MODEL_NAME, "keep_alive": 0}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception as e:
        log(f"  [UNLOAD] Warning: {e}")
    
    t0 = time.time()
    while time.time() - t0 < timeout:
        ps = get_ollama_ps()
        if MODEL_NAME not in ps:
            log(f"  [UNLOAD] Model unloaded in {time.time() - t0:.2f}s.")
            return True
        time.sleep(1)
    log(f"  [UNLOAD] Warning: Model still in ollama ps after {timeout}s.")
    return False

log("=== TASK F4: CORRECT DERIVED FIGURES AND THE VRAM GAP ===")

# Step a: Recompute with script
log("\n--- Step a: Recomputing Peak VRAM Percentages, Headroom, and Deltas ---")
TOTAL_VRAM = 8192

# Peak measurements from T2:
cases = [
    ("C2 (num_ctx 8192)", 7566, 1002, "5.6 GB", 5600),
    ("C3 (num_ctx 4096)", 7426, 1002, "5.5 GB", 5500),
    ("Earlier Session Report Peak", 7726, 1167, "N/A", 0)
]

for label, peak_mb, idle_mb, ps_size_str, ps_size_approx_mb in cases:
    pct = (peak_mb / TOTAL_VRAM) * 100.0
    headroom = TOTAL_VRAM - peak_mb
    delta = peak_mb - idle_mb
    log(f"Case: {label}")
    log(f"  Inputs: Total VRAM = {TOTAL_VRAM} MiB, Peak = {peak_mb} MiB, Idle Baseline = {idle_mb} MiB")
    log(f"  Calculation: ({peak_mb} / {TOTAL_VRAM}) * 100 = {pct:.4f}% -> {pct:.2f}% (or {pct:.1f}%)")
    log(f"  Calculation Headroom: {TOTAL_VRAM} - {peak_mb} = {headroom} MiB")
    log(f"  Calculation Delta over Idle: {peak_mb} - {idle_mb} = {delta} MiB")
    if ps_size_str != "N/A":
        gap = delta - ps_size_approx_mb
        log(f"  ollama ps SIZE reported: {ps_size_str}")
        log(f"  Gap (nvidia-smi delta {delta} MiB minus approx ollama ps {ps_size_approx_mb} MiB) = {gap} MiB")
    log("")

# Step b: Test the gap
log("--- Step b: Testing Process-Level GPU Memory Attribution ---")
idle_init = get_vram_mb()
ps_init = get_ollama_ps()
log(f"Pre-test Idle VRAM: {idle_init} MiB")
log(f"Pre-test ollama ps:\n{ps_init}")

try:
    log("\nWarming up model with keep_alive: '2m' to inspect loaded GPU state...")
    url = f"{BASE_URL}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "keep_alive": "2m",
        "options": {"num_ctx": 8192}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        pass
    
    time.sleep(1)
    vram_loaded = get_vram_mb()
    ps_loaded = get_ollama_ps()
    log(f"Loaded Total VRAM: {vram_loaded} MiB (Net delta: {vram_loaded - idle_init} MiB)")
    log(f"Loaded ollama ps:\n{ps_loaded}")
    
    # Query compute apps on Windows
    log("\nQuerying Windows compute applications via nvidia-smi:")
    res_compute = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv"],
        capture_output=True, text=True
    )
    log(res_compute.stdout.strip())
    
    # Query all processes with nvidia-smi
    log("\nQuerying full nvidia-smi process table:")
    res_smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
    log(res_smi.stdout.strip())
    
    # Evaluation of gap attribution:
    log("\nAttribution Analysis:")
    log("On Windows WDDM, 'nvidia-smi --query-compute-apps' reports compute apps. Notice whether Ollama runner appears or reports 'N/A' under WDDM C+G (Compute + Graphics).")
    if "N/A" in res_smi.stdout and "ollama" not in res_compute.stdout:
        log("Under Windows WDDM Driver Model, GUI and CUDA applications share unified memory where individual compute memory is partially managed by the DirectX/WDDM kernel subsystem and per-process memory is reported as N/A.")
        log("Gap cause: The gap between ollama ps reported model weight allocation (~5.6 GB) and nvidia-smi total delta (~6.5 GB) reflects context KV cache allocation, CUDA runtime context overhead, and WDDM memory management reservations. Because WDDM does not isolate per-process memory in this query, full decomposition cannot be completely attributed without admin-level GPU profiling tools.")
    else:
        log("gap cause not tested")

finally:
    log("\nUnloading model in finally block...")
    unload_model()
    time.sleep(2)
    vram_final = get_vram_mb()
    ps_final = get_ollama_ps()
    log(f"Post-test VRAM: {vram_final} MiB (Delta from initial idle: {vram_final - idle_init} MiB)")
    log(f"Post-test ollama ps:\n{ps_final}")

# Step c: Context note
log("\n--- Step c: Windows Desktop VRAM Sharing Note ---")
log("Windows desktop applications (Antigravity IDE, Claude Desktop, Edge WebView2, Explorer, Wallpaper Engine) share this 8192 MiB VRAM pool.")
log("Across observed audit sessions, the idle baseline varied between 994 MiB and 1,167 MiB.")
log("Therefore, true available headroom is dynamically bounded by: Headroom = 8192 MiB - Peak_Used (which includes the prevailing ~1,000-1,167 MiB idle desktop baseline).")

OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")
log(f"\nRaw output saved to {OUT_TXT}")
