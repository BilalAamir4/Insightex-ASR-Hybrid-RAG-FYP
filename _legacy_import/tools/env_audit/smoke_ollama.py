import urllib.request
import json
import time
import subprocess

def get_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,nounits,noheader"],
            encoding='utf-8'
        )
        used, total = out.strip().split(',')
        return float(used.strip()), float(total.strip())
    except Exception as e:
        return None, None

vram_idle, vram_total = get_vram()
print(f"Initial Idle VRAM: {vram_idle} MiB / {vram_total} MiB", flush=True)

# 1. Inspect model parameters / context length via /api/show
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/show",
    data=json.dumps({"name": "qwen3.5:latest"}).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as resp:
    info = json.loads(resp.read().decode('utf-8'))
    print("\n--- Model Show Info ---", flush=True)
    modelfile = info.get("modelfile", "")
    params = info.get("parameters", "")
    details = info.get("details", {})
    print(f"Family: {details.get('family')}, Parameter size: {details.get('parameter_size')}, Quantization: {details.get('quantization_level')}")
    print(f"Modelfile context params / settings:\n{params}")

# 2. Test JSON structured output inference
prompt = "Extract key concepts from this Urdu-English lecture sentence: 'Aaj hum binary search tree ke baare mein parhenge, jo ek hierarchical data structure hai.' Return a JSON object with a key 'concepts' which is a list of strings."

payload = {
    "model": "qwen3.5:latest",
    "prompt": prompt,
    "stream": False,
    "format": "json",
    "options": {
        "temperature": 0.2
    }
}

print("\n--- Sending Generation Request (JSON mode) ---", flush=True)
t0 = time.time()
req2 = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(payload).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req2) as resp:
    gen_result = json.loads(resp.read().decode('utf-8'))
    t_gen = time.time() - t0

vram_loaded, _ = get_vram()
print(f"Inference completed in {t_gen:.2f}s", flush=True)
print(f"Peak VRAM during/after load: {vram_loaded} MiB (Delta: {vram_loaded - vram_idle:+.1f} MiB)", flush=True)
print(f"Eval count: {gen_result.get('eval_count')} tokens, Prompt eval count: {gen_result.get('prompt_eval_count')} tokens", flush=True)
print(f"Response:\n{gen_result.get('response')}", flush=True)

# Verify JSON parsing
try:
    parsed = json.loads(gen_result.get('response', '{}'))
    print(f"JSON validation: PASSED! Extracted concepts: {parsed.get('concepts')}", flush=True)
except Exception as e:
    print(f"JSON validation: FAILED ({e})", flush=True)

# 3. Check /api/ps to see loaded model and actual running context window
req_ps = urllib.request.Request("http://127.0.0.1:11434/api/ps")
with urllib.request.urlopen(req_ps) as resp:
    ps_data = json.loads(resp.read().decode('utf-8'))
    print("\n--- Running Models (/api/ps) ---", flush=True)
    print(json.dumps(ps_data, indent=2), flush=True)

# 4. Unload model (keep_alive: 0)
print("\n--- Unloading Model (keep_alive=0) ---", flush=True)
unload_payload = {
    "model": "qwen3.5:latest",
    "keep_alive": 0
}
req_unload = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(unload_payload).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req_unload) as resp:
    pass

time.sleep(2)
vram_after_unload, _ = get_vram()
print(f"VRAM after unload: {vram_after_unload} MiB (Initial idle: {vram_idle} MiB, Diff: {vram_after_unload - vram_idle:+.1f} MiB)", flush=True)
if abs(vram_after_unload - vram_idle) < 200:
    print("SUCCESS: VRAM cleanly released back to idle baseline!", flush=True)
else:
    print("WARNING: VRAM did not return to baseline!", flush=True)
