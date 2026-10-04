#!/usr/bin/env python3
"""
Whisper real-speech benchmark v2: 3 runs per model (cold + 2 warm).
Each model runs in its own subprocess for VRAM isolation.
Settings: language=ur, beam_size=5, vad_filter=True, word_timestamps=True.
"""
import os
import sys
import time
import json
import subprocess
import threading

AUDIO_FILE = "/mnt/e/FYP/data/day04_batch_vs_online/eval/clip_30s.wav"
AUDIO_DURATION_S = 30.0
CACHE_DIR = os.path.expanduser("~/cache/huggingface/hub")
NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"
NUM_RUNS = 3

def get_vram_mb():
    try:
        out = subprocess.check_output(
            [NVIDIA_SMI, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0


class VRAMMonitor:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.stop_event = threading.Event()
        self.peak_vram = 0
        self.baseline_vram = 0

    def _monitor(self):
        while not self.stop_event.is_set():
            v = get_vram_mb()
            if v > self.peak_vram:
                self.peak_vram = v
            time.sleep(self.interval)

    def start(self):
        self.baseline_vram = get_vram_mb()
        self.peak_vram = self.baseline_vram
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        end_vram = get_vram_mb()
        return {
            "baseline_mb": self.baseline_vram,
            "peak_mb": self.peak_vram,
            "delta_mb": self.peak_vram - self.baseline_vram,
            "end_mb": end_vram,
        }


def run_single_model(model_size, compute_type="float16"):
    """Run inside a subprocess — one model at a time, 3 transcription runs."""
    from faster_whisper import WhisperModel

    pre_load_vram = get_vram_mb()
    print(f"\n{'='*60}")
    print(f"  Whisper '{model_size}' | compute={compute_type} | CUDA")
    print(f"  Audio: {AUDIO_FILE} ({AUDIO_DURATION_S}s)")
    print(f"  Pre-load VRAM: {pre_load_vram} MiB")
    print(f"{'='*60}")

    mon = VRAMMonitor()
    mon.start()

    # --- Load ---
    t0 = time.time()
    model = WhisperModel(
        model_size,
        device="cuda",
        compute_type=compute_type,
        download_root=CACHE_DIR,
    )
    load_time = time.time() - t0
    print(f"  Load time: {load_time:.2f}s")

    # --- Transcribe NUM_RUNS times ---
    runs = []
    all_segments = None
    for run_idx in range(1, NUM_RUNS + 1):
        t1 = time.time()
        segments, info = model.transcribe(
            AUDIO_FILE,
            language="ur",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        seg_list = list(segments)
        infer_time = time.time() - t1
        rtf = AUDIO_DURATION_S / infer_time if infer_time > 0 else 0

        label = "cold" if run_idx == 1 else f"warm-{run_idx - 1}"
        runs.append({
            "run": run_idx,
            "label": label,
            "infer_time_s": round(infer_time, 2),
            "rtf": round(rtf, 2),
            "num_segments": len(seg_list),
        })
        print(f"  Run {run_idx} ({label}): {infer_time:.2f}s  RTF={rtf:.2f}x  segments={len(seg_list)}")

        if run_idx == 1:
            all_segments = seg_list  # keep first run's segments for display

    # Show first 3 segments from cold run
    has_urdu = any("\u0600" <= ch <= "\u06FF" for seg in all_segments for ch in seg.text)
    print(f"\n  --- First 3 segments (cold run) ---")
    first_3 = []
    for seg in all_segments[:3]:
        print(f"  [{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text.strip()}")
        first_3.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})

    print(f"\n  Contains Urdu script: {has_urdu}")
    print(f"  Detected language: {info.language} (prob={info.language_probability:.2f})")

    # Cleanup
    del model
    time.sleep(2)
    stats = mon.stop()
    print(f"\n  VRAM pre-load:  {pre_load_vram} MiB")
    print(f"  VRAM baseline:  {stats['baseline_mb']} MiB")
    print(f"  VRAM peak:      {stats['peak_mb']} MiB (+{stats['delta_mb']} MiB)")
    print(f"  VRAM after:     {stats['end_mb']} MiB")

    status = "PASS" if len(all_segments) > 0 and has_urdu else "FAIL"
    print(f"\n  STATUS: {status}")

    result = {
        "model": model_size,
        "compute_type": compute_type,
        "load_time_s": round(load_time, 2),
        "runs": runs,
        "num_segments": len(all_segments),
        "has_urdu": has_urdu,
        "pre_load_vram_mb": pre_load_vram,
        "vram_baseline_mb": stats["baseline_mb"],
        "vram_peak_mb": stats["peak_mb"],
        "vram_delta_mb": stats["delta_mb"],
        "vram_after_mb": stats["end_mb"],
        "first_3_segments": first_3,
        "status": status,
    }
    print(f"\n__RESULT_JSON__:{json.dumps(result)}")
    return result


def run_in_subprocess(model_size, compute_type="float16"):
    """Spawn a fresh Python process for VRAM isolation."""
    script = os.path.abspath(__file__)
    env = os.environ.copy()
    cmd = [sys.executable, script, "--run-single", model_size, compute_type]
    print(f"\n>>> Launching subprocess for {model_size} ({compute_type})...")
    print(f"    Python: {sys.executable}")
    idle_vram = get_vram_mb()
    print(f"    Idle VRAM before launch: {idle_vram} MiB")
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=600)
    print(proc.stdout)
    if proc.stderr:
        # Filter out UserWarnings from ctranslate2
        important = [l for l in proc.stderr.splitlines() if "UserWarning" not in l and "warnings.warn" not in l]
        if important:
            print("STDERR:", "\n".join(important[-10:]))

    for line in proc.stdout.splitlines():
        if line.startswith("__RESULT_JSON__:"):
            return json.loads(line.split(":", 1)[1])
    return {"status": "ERROR", "model": model_size, "returncode": proc.returncode}


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--run-single":
        model_size = sys.argv[2]
        compute_type = sys.argv[3]

        # Print environment confirmation
        import sysconfig
        venv = os.environ.get("VIRTUAL_ENV", "(none)")
        print(f"  [ENV] VIRTUAL_ENV={venv}")
        print(f"  [ENV] Python={sys.executable}")
        print(f"  [ENV] site-packages={sysconfig.get_path('purelib')}")
        try:
            import av
            print(f"  [ENV] av=={av.__version__}")
        except ImportError:
            print(f"  [ENV] av: NOT INSTALLED")
        try:
            import faster_whisper
            print(f"  [ENV] faster-whisper=={faster_whisper.__version__}")
        except Exception:
            pass

        run_single_model(model_size, compute_type)
    else:
        if not os.path.exists(AUDIO_FILE):
            print(f"ERROR: Audio file not found: {AUDIO_FILE}")
            sys.exit(1)

        print(f"Audio file: {AUDIO_FILE}")
        print(f"Audio duration: {AUDIO_DURATION_S}s")
        print(f"Runs per model: {NUM_RUNS} (run 1 = cold, runs 2-3 = warm)")
        print(f"Global idle VRAM: {get_vram_mb()} MiB")

        results = []

        # Run medium
        r = run_in_subprocess("medium", "float16")
        results.append(r)

        time.sleep(3)

        # Run large-v3
        r = run_in_subprocess("large-v3", "float16")
        results.append(r)

        # If large-v3 peaked above 7000 MiB, also test int8_float16
        if r.get("vram_peak_mb", 0) > 7000:
            print("\n>>> large-v3 float16 peaked above 7 GB - testing int8_float16...")
            time.sleep(3)
            r2 = run_in_subprocess("large-v3", "int8_float16")
            results.append(r2)

        time.sleep(3)
        final_vram = get_vram_mb()
        print(f"\n{'='*60}")
        print(f"  FINAL VRAM: {final_vram} MiB")
        print(f"{'='*60}")

        # Summary table
        print(f"\n{'='*60}")
        print(f"  SUMMARY (3 runs: cold / warm-1 / warm-2)")
        print(f"{'='*60}")
        hdr = f"  {'Model':<22} {'Load(s)':<9} {'Cold(s)':<9} {'W1(s)':<9} {'W2(s)':<9} {'RTF(W)':<9} {'Peak VRAM':<12} {'Status'}"
        print(hdr)
        print(f"  {'-'*88}")
        for r in results:
            label = f"{r.get('model','?')} ({r.get('compute_type','?')})"
            runs = r.get("runs", [])
            cold = runs[0]["infer_time_s"] if len(runs) > 0 else "?"
            w1   = runs[1]["infer_time_s"] if len(runs) > 1 else "?"
            w2   = runs[2]["infer_time_s"] if len(runs) > 2 else "?"
            # RTF from warm runs average
            warm_rtfs = [ru["rtf"] for ru in runs[1:] if "rtf" in ru]
            avg_rtf = round(sum(warm_rtfs) / len(warm_rtfs), 2) if warm_rtfs else "?"
            peak = str(r.get("vram_peak_mb", "?")) + " MiB"
            print(f"  {label:<22} {str(r.get('load_time_s','?')):<9} {str(cold):<9} {str(w1):<9} {str(w2):<9} {str(avg_rtf)+'x':<9} {peak:<12} {r.get('status','?')}")
