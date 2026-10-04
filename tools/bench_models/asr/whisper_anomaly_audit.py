#!/usr/bin/env python3
"""
TASK T3: Whisper Speed Anomaly Investigation (Data Only)
Investigates medium vs large-v3 timing on clip_30s.wav across:
- Order 1: large-v3 then medium
- Order 2: medium then large-v3
- Extra: medium with temperature=0.0 (no fallback)
5 runs per model per process (run 1 cold, runs 2-5 warm).
"""
import os
import sys
import time
import json
import subprocess
from pathlib import Path
import numpy as np

AUDIO_FILE = os.path.join(os.environ["INSIGHTEX_DATA"], "eval/day04_batch_vs_online/eval/clip_30s.wav")
AUDIO_DURATION_S = 30.0
CACHE_DIR = os.path.expanduser("~/cache/huggingface/hub")
NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"
OUT_FILE = Path(os.environ["INSIGHTEX_DATA"]) / "logs/env_audit/followup/T3.txt"
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

out_lines = []
def log(msg=""):
    print(msg, flush=True)
    out_lines.append(msg)

def get_gpu_telemetry():
    try:
        query = "pstate,clocks.gr,clocks.mem,temperature.gpu,memory.used"
        out = subprocess.check_output(
            [NVIDIA_SMI, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        ).strip()
        parts = [p.strip() for p in out.split(",")]
        # Also get processes
        procs = subprocess.check_output(
            [NVIDIA_SMI, "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
            text=True, timeout=5
        ).strip()
        return {
            "pstate": parts[0],
            "clock_gr_mhz": parts[1],
            "clock_mem_mhz": parts[2],
            "temp_c": parts[3],
            "vram_used_mb": parts[4],
            "processes": procs if procs else "(none)"
        }
    except Exception as e:
        return {"error": str(e)}

def run_worker_process(model_size, order_label, temp_override=None):
    """Executes a single model run inside its own Python process."""
    from faster_whisper import WhisperModel
    import numpy as np

    telemetry_before = get_gpu_telemetry()
    log(f"\n{'='*70}")
    log(f"SUBPROCESS: {model_size} | Order: {order_label} | temp_override={temp_override}")
    log(f"{'='*70}")
    log("GPU State Before Process:")
    log(f"  PState: {telemetry_before.get('pstate')}, Clocks(Graphics/Mem): {telemetry_before.get('clock_gr_mhz')} MHz / {telemetry_before.get('clock_mem_mhz')} MHz")
    log(f"  Temp: {telemetry_before.get('temp_c')} C, VRAM Used: {telemetry_before.get('vram_used_mb')} MiB, Active Compute Procs: {telemetry_before.get('processes')}")

    t_load0 = time.time()
    model = WhisperModel(
        model_size,
        device="cuda",
        compute_type="float16",
        download_root=CACHE_DIR
    )
    load_time = time.time() - t_load0
    log(f"Model Load Time: {load_time:.2f}s")

    runs_data = []
    
    for r_idx in range(1, 6):
        is_cold = (r_idx == 1)
        r_label = "cold" if is_cold else f"warm-{r_idx-1}"
        
        t0 = time.time()
        kwargs = {
            "language": "ur",
            "beam_size": 5,
            "vad_filter": True,
            "word_timestamps": True
        }
        if temp_override is not None:
            kwargs["temperature"] = temp_override

        segments, info = model.transcribe(AUDIO_FILE, **kwargs)
        seg_list = list(segments)
        elapsed = time.time() - t0
        
        speed_factor = AUDIO_DURATION_S / elapsed if elapsed > 0 else 0
        rtf = elapsed / AUDIO_DURATION_S if AUDIO_DURATION_S > 0 else 0
        
        # Segment diagnostics
        temps = [getattr(s, "temperature", 0.0) for s in seg_list]
        max_temp = max(temps) if temps else 0.0
        segs_temp_gt_0 = sum(1 for t in temps if t > 0.0)
        
        avg_logprobs = [getattr(s, "avg_logprob", 0.0) for s in seg_list]
        comp_ratios = [getattr(s, "compression_ratio", 0.0) for s in seg_list]
        no_speeches = [getattr(s, "no_speech_prob", 0.0) for s in seg_list]
        
        run_record = {
            "run": r_idx,
            "label": r_label,
            "elapsed_s": round(elapsed, 2),
            "speed_factor_x": round(speed_factor, 2),
            "rtf": round(rtf, 4),
            "num_segments": len(seg_list),
            "max_temp": round(max_temp, 2),
            "segs_temp_gt_0": segs_temp_gt_0,
            "avg_logprob_mean": round(float(np.mean(avg_logprobs)), 3) if avg_logprobs else 0.0,
            "compression_ratio_mean": round(float(np.mean(comp_ratios)), 3) if comp_ratios else 0.0,
            "no_speech_mean": round(float(np.mean(no_speeches)), 3) if no_speeches else 0.0,
        }
        runs_data.append(run_record)
        
        log(f"  Run {r_idx} ({r_label:<6}): {elapsed:5.2f}s | Speed: {speed_factor:5.2f}x real time | RTF: {rtf:.4f} | "
            f"Segs: {len(seg_list):2d} | MaxTemp: {max_temp:.2f} | SegsTemp>0: {segs_temp_gt_0} | "
            f"AvgLogProb: {run_record['avg_logprob_mean']:6.3f} | CompRatio: {run_record['compression_ratio_mean']:5.2f}")

    del model
    time.sleep(2)
    telemetry_after = get_gpu_telemetry()
    log("GPU State After Process Exit:")
    log(f"  PState: {telemetry_after.get('pstate')}, VRAM Used: {telemetry_after.get('vram_used_mb')} MiB (Delta: {int(telemetry_after.get('vram_used_mb',0)) - int(telemetry_before.get('vram_used_mb',0))} MiB)")

    return {
        "model": model_size,
        "order": order_label,
        "temp_override": temp_override,
        "load_time_s": round(load_time, 2),
        "runs": runs_data
    }

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--worker":
        # Worker subprocess
        model_size = sys.argv[2]
        order_label = sys.argv[3]
        temp_override = float(sys.argv[4]) if len(sys.argv) > 4 else None
        res = run_worker_process(model_size, order_label, temp_override)
        print("__RESULT__:" + json.dumps(res))
    else:
        # Parent Orchestrator
        log("======================================================================")
        log("TASK T3: WHISPER SPEED ANOMALY BENCHMARK (DATA ONLY)")
        log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        log(f"Audio File: {AUDIO_FILE} ({AUDIO_DURATION_S}s)")
        log("======================================================================\n")
        
        script = os.path.abspath(__file__)
        tasks = [
            # Pair 1: large-v3 first, then medium
            ("large-v3", "Order1 (large-v3 -> medium)", None),
            ("medium",   "Order1 (large-v3 -> medium)", None),
            # Pair 2: medium first, then large-v3
            ("medium",   "Order2 (medium -> large-v3)", None),
            ("large-v3", "Order2 (medium -> large-v3)", None),
            # Extra: medium with temperature=0.0 (no fallback)
            ("medium",   "Extra (medium temp=0.0)", 0.0),
        ]
        
        all_results = []
        for model_size, order_label, temp_override in tasks:
            cmd = [sys.executable, script, "--worker", model_size, order_label]
            if temp_override is not None:
                cmd.append(str(temp_override))
            
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=600)
            log(proc.stdout)
            if proc.stderr:
                err_lines = [l for l in proc.stderr.splitlines() if "UserWarning" not in l and "warnings.warn" not in l]
                if err_lines:
                    log("STDERR: " + "\n".join(err_lines[-5:]))
                    
            for line in proc.stdout.splitlines():
                if line.startswith("__RESULT__:"):
                    all_results.append(json.loads(line[len("__RESULT__:"):].strip()))
                    break
            time.sleep(3)
            
        log("\n======================================================================")
        log("TASK T3 SUMMARY DATA TABLE")
        log("======================================================================")
        log(f"{'Model & Run Setting':<36} {'Order':<28} {'Cold (s)':<9} {'Warm Med':<9} {'Warm Min-Max (s)':<18} {'Speed (x real)':<15} {'RTF (warm med)'}")
        log("-" * 130)
        
        for r in all_results:
            m_label = f"{r['model']} (temp={r['temp_override']})" if r['temp_override'] is not None else r['model']
            runs = r['runs']
            cold_time = runs[0]['elapsed_s']
            warm_times = [ru['elapsed_s'] for ru in runs[1:]]
            warm_med = round(float(np.median(warm_times)), 2)
            warm_min = min(warm_times)
            warm_max = max(warm_times)
            warm_speeds = [ru['speed_factor_x'] for ru in runs[1:]]
            med_speed = round(float(np.median(warm_speeds)), 2)
            med_rtf = round(warm_med / AUDIO_DURATION_S, 4)
            
            log(f"{m_label:<36} {r['order']:<28} {cold_time:<9.2f} {warm_med:<9.2f} {f'{warm_min:.2f}-{warm_max:.2f}s':<18} {f'{med_speed:.2f}x':<15} {med_rtf:.4f}")

        # Summary of temperature fallbacks
        log("\n--- TEMPERATURE FALLBACK OCCURRENCES ---")
        for r in all_results:
            m_label = f"{r['model']} ({r['order']})"
            runs = r['runs']
            max_temps = [ru['max_temp'] for ru in runs]
            gt0_counts = [ru['segs_temp_gt_0'] for ru in runs]
            log(f"{m_label:<45} | Max temps seen: {max_temps} | Segments with temp>0: {gt0_counts}")
            
        log("\n--- DATA-ONLY CONCLUSION ---")
        log("Reported the empirical data as measured. Cause not tested.")
        log("No generalized speed or quality claim is made beyond this specific 30.0s clip.")
        
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")
        log(f"\nSaved raw output to {OUT_FILE}")
