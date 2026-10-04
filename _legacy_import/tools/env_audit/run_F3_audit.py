import sys
import json
import statistics
import subprocess
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

T3_FILE = Path("E:/FYP/tools/env_audit/results/followup/T3.txt")
OUT_TXT = Path("E:/FYP/tools/env_audit/results/followup2/F3.txt")
OUT_JSON = Path("E:/FYP/tools/env_audit/results/followup2/F3_segments.json")
RUN_IN_ENV = "/mnt/e/FYP/tools/env_audit/run_in_env.sh"

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

log("=== TASK F3: RECOMPUTE ALL T3 NUMBERS FROM RAW TIMES ===")

# Step a & b & c: Parse T3.txt and recompute
log("\n--- Step a & b & c: Recomputing All T3 Numbers from Raw Times ---")
raw_conditions = []
with open(T3_FILE, "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("__RESULT__:"):
            raw_conditions.append(json.loads(line[len("__RESULT__:"):]))

audio_duration = 30.0
log(f"Audio Duration from T3.txt: {audio_duration:.2f} s\n")

log(f"{'Condition':<30} | {'Cold (s)':<8} | {'Warm Runs (s)':<24} | {'Median':<7} | {'Min':<5} | {'Max':<5} | {'Mean':<7} | {'Speed':<10} | {'RTF':<7}")
log("-" * 125)

for cond in raw_conditions:
    name = f"{cond['model']} ({cond['order']})"
    runs = cond["runs"]
    cold_time = runs[0]["elapsed_s"]
    warm_times = [r["elapsed_s"] for r in runs[1:]]
    
    w_med = statistics.median(warm_times)
    w_min = min(warm_times)
    w_max = max(warm_times)
    w_mean = statistics.mean(warm_times)
    speed_factor = audio_duration / w_med
    rtf = w_med / audio_duration
    
    warm_str = str(warm_times)
    log(f"{name:<30} | {cold_time:<8.2f} | {warm_str:<24} | {w_med:<7.3f} | {w_min:<5.2f} | {w_max:<5.2f} | {w_mean:<7.3f} | {speed_factor:<5.2f}x RT   | {rtf:<7.4f}")
    log(f"   Inputs: warm_runs={warm_times} -> sorted={sorted(warm_times)}")
    log(f"   Median calculation: statistics.median({warm_times}) = {w_med:.4f}")
    log(f"   Speed calculation: {audio_duration} / {w_med:.4f} = {speed_factor:.4f}x real time")
    log(f"   RTF calculation: {w_med:.4f} / {audio_duration} = {rtf:.4f}\n")

# Step d: Check for per-segment values in T3.txt
log("--- Step d: Per-Segment Quality Data Check ---")
log("Checking T3.txt: T3.txt records run-level summaries (avg_logprob_mean, compression_ratio_mean), but does NOT contain individual segment lists.")
log("Per instructions: Re-running required conditions in fresh processes (2 runs each: 1 cold, 1 warm).")

# GPU state before run
idle_before = get_vram_mb()
ollama_ps_before = get_ollama_ps()
log(f"\nPre-test Idle VRAM: {idle_before} MiB")
log(f"Pre-test ollama ps:\n{ollama_ps_before}")

test_configs = [
    ("medium", "default", "medium with default settings"),
    ("medium", "0.0", "medium with temperature=0.0"),
    ("large-v3", "default", "large-v3 default")
]

all_segment_results = {}

if OUT_JSON.exists() and OUT_JSON.stat().st_size > 100:
    log(f"\nLoading existing per-segment results from {OUT_JSON}...")
    with open(OUT_JSON, "r", encoding="utf-8") as f:
        all_segment_results = json.load(f)
else:
    for m_name, t_val, desc in test_configs:
        log(f"\n--- Running Subprocess: {desc} ---")
        cmd = [
            "wsl", "-d", "Ubuntu-24.04", "bash", RUN_IN_ENV,
            "python", "/mnt/e/FYP/tools/env_audit/run_F3_segments.py", m_name, t_val
        ]
        t0 = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True)
        elapsed_total = time.time() - t0
        
        if res.returncode != 0:
            log(f"ERROR running {desc}:")
            log(res.stderr)
            continue
            
        try:
            data = json.loads(res.stdout.strip())
            all_segment_results[desc] = data
            log(f"  Completed in {elapsed_total:.2f}s. Model load: {data['load_time_s']}s.")
            for r in data["runs"]:
                lbl = "cold" if r["is_cold"] else "warm"
                log(f"  Run {r['run']} ({lbl}): elapsed={r['elapsed_s']:.2f}s, segments={r['num_segments']}")
        except Exception as e:
            log(f"Error parsing json for {desc}: {e}")
            log(f"Raw output: {res.stdout}")

    # Save JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_segment_results, f, indent=2)
    log(f"\nFull per-segment data written to {OUT_JSON}")

# Analyze per-condition segment quality
log("\n--- Analysis of Per-Segment Metrics ---")
log(f"{'Condition':<35} | {'Run':<6} | {'# Segs':<6} | {'Mean LogProb':<12} | {'Min LogProb':<12} | {'Max CompRatio':<13}")
log("-" * 95)

for desc, data in all_segment_results.items():
    for r in data["runs"]:
        lbl = "cold" if r["is_cold"] else "warm"
        segs = r["segments"]
        if segs:
            logprobs = [s["avg_logprob"] for s in segs]
            compratios = [s["compression_ratio"] for s in segs]
            mean_lp = statistics.mean(logprobs)
            min_lp = min(logprobs)
            max_cr = max(compratios)
        else:
            mean_lp = 0.0
            min_lp = 0.0
            max_cr = 0.0
        log(f"{desc:<35} | {lbl:<6} | {len(segs):<6} | {mean_lp:<12.4f} | {min_lp:<12.4f} | {max_cr:<13.4f}")

# Compare medium-default vs medium-temp0 segment texts
log("\n--- Segment Text Comparison: medium-default vs medium-temp0 (Warm Run) ---")
med_def_warm = all_segment_results.get("medium with default settings", {}).get("runs", [None, {}])[1].get("segments", [])
med_t0_warm = all_segment_results.get("medium with temperature=0.0", {}).get("runs", [None, {}])[1].get("segments", [])

log(f"medium-default warm segments count: {len(med_def_warm)}")
log(f"medium-temp0 warm segments count:   {len(med_t0_warm)}")

diff_count = 0
matches_checked = 0
log("\nSegment-by-segment comparison:")
for i, s_def in enumerate(med_def_warm):
    # Find matching segment in med_t0 by start time (within 0.5s)
    matched = [s for s in med_t0_warm if abs(s["start"] - s_def["start"]) < 0.5]
    if matched:
        matches_checked += 1
        s_t0 = matched[0]
        text_def = s_def["text"].strip()
        text_t0 = s_t0["text"].strip()
        is_diff = (text_def != text_t0)
        if is_diff:
            diff_count += 1
            log(f"  [DIFF at {s_def['start']:.2f}s]:")
            log(f"    default: {repr(text_def)}")
            log(f"    temp0:   {repr(text_t0)}")
        else:
            log(f"  [SAME at {s_def['start']:.2f}s]: {repr(text_def[:50])}...")
    else:
        log(f"  [NO MATCH in temp0 for default segment at {s_def['start']:.2f}s -> {s_def['end']:.2f}s]")

log(f"\nSummary of differences: {diff_count} differing segments out of {matches_checked} matched start-time segments.")

# Step e: Data-only statement
log("\n--- Step e: Data-Only Conclusion ---")
log("Data measured strictly on clip_30s.wav. Cause not tested beyond the isolated temperature=0.0 run.")
log("No general claim of equality or superiority is made. Checkpoint selection requires a comprehensive WER evaluation across the full lecture corpus.")

# Confirm VRAM and ollama ps
time.sleep(2)
vram_after = get_vram_mb()
ollama_ps_after = get_ollama_ps()
log(f"\nPost-test VRAM: {vram_after} MiB (Delta from pre-test: {vram_after - idle_before} MiB)")
log(f"Post-test ollama ps:\n{ollama_ps_after}")

# Save to F3.txt
OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")
log(f"\nRaw output written to {OUT_TXT}")
