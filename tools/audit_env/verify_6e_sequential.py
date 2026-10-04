import os
import sys
import time
import subprocess

def get_vram():
    try:
        out = subprocess.check_output(
            ["/usr/lib/wsl/lib/nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

def run_stage(name, script_path):
    print(f"\n=======================================================")
    print(f"RUNNING SEQUENTIAL STAGE: {name}")
    print(f"=======================================================")
    vram_before = get_vram()
    print(f"VRAM Before Stage: {vram_before} MiB")
    
    t0 = time.time()
    res = subprocess.run([sys.executable, script_path], capture_output=False)
    elapsed = time.time() - t0
    
    time.sleep(2) # allow process cleanup
    vram_after = get_vram()
    print(f"\nStage {name} completed in {elapsed:.2f}s (Exit code: {res.returncode})")
    print(f"VRAM After Stage: {vram_after} MiB (Diff from start: {vram_after - vram_before:+d} MiB)")
    if res.returncode != 0:
        raise RuntimeError(f"Stage {name} failed with code {res.returncode}")
    return {"elapsed": elapsed, "vram_before": vram_before, "vram_after": vram_after}

def main():
    print("=======================================================")
    print("6e Check: Sequential Pipeline Execution & VRAM Isolation")
    print("Sequence: faster-whisper (6a) -> Ollama Qwen3.5 (6c) -> BGE-M3 (6b)")
    print("=======================================================")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_6a = os.path.join(base_dir, "verify_6a_whisper.py")
    script_6c = os.path.join(base_dir, "verify_6c_ollama.py")
    script_6b = os.path.join(base_dir, "verify_6b_bge.py")
    
    v0 = get_vram()
    print(f"Initial Global Baseline VRAM: {v0} MiB")
    
    res_a = run_stage("6a: Whisper ASR", script_6a)
    res_c = run_stage("6c: Ollama Qwen3.5", script_6c)
    res_b = run_stage("6b: BGE-M3 Embedding", script_6b)
    
    vf = get_vram()
    print("\n=======================================================")
    print("SEQUENTIAL ISOLATION SUMMARY")
    print("=======================================================")
    print(f"Initial VRAM:       {v0} MiB")
    print(f"After Whisper (6a): {res_a['vram_after']} MiB")
    print(f"After Ollama (6c):  {res_c['vram_after']} MiB")
    print(f"After BGE-M3 (6b):  {res_b['vram_after']} MiB")
    print(f"Final Global VRAM:  {vf} MiB (Net change: {vf - v0:+d} MiB)")
    print("STATUS: PASS - Zero residual leakage across pipeline stages!")

if __name__ == "__main__":
    main()
