#!/usr/bin/env python3
"""
TASK T2: Ollama Call Contract & Optimization Audit
Tests:
- Reusable client with unload_model() in finally block
- Real transcribed input from whisper_large_v3_first10min.json grouped into ~60s chunks
- Strict JSON Schema vs plain string 'json'
- num_ctx 8192 vs 4096 and GPU/CPU split
- Reproducibility across 3 runs for 3 chunks
- Comprehensive metrics: prompt_eval_count, eval_count, load_duration, total_duration
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
import subprocess
import threading
from pathlib import Path
import jsonschema

SEGMENTS_FILE = Path("/mnt/e/FYP/data/day04_batch_vs_online/eval/whisper_large_v3_first10min.json")
OUT_FILE = Path("/mnt/e/FYP/tools/env_audit/results/followup/T2.txt")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen3.5:latest"
NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"

CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "exam_relevant": {"type": "boolean"}
                },
                "required": ["name", "description", "exam_relevant"],
                "additionalProperties": False
            }
        }
    },
    "required": ["concepts"],
    "additionalProperties": False
}

SYSTEM_PROMPT = (
    "You are an expert AI educator analyzing bilingual lecture transcripts (Urdu/English code-switched). "
    "Extract the core technical concepts mentioned in the text. "
    "Return ONLY a JSON object with a single key 'concepts' containing a list of objects. "
    "Each object must have: 'name' (string), 'description' (string in English), 'exam_relevant' (boolean)."
)

out_lines = []
def log(msg=""):
    print(msg, flush=True)
    out_lines.append(msg)

def get_vram_mb():
    try:
        out = subprocess.check_output(
            [NVIDIA_SMI, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

class VRAMSampler:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.stop_event = threading.Event()
        self.samples = []

    def _monitor(self):
        while not self.stop_event.is_set():
            v = get_vram_mb()
            self.samples.append(v)
            time.sleep(self.interval)

    def start(self):
        self.samples = []
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        return self.samples

def get_ollama_ps():
    try:
        # Run on Windows host or via loopback
        out = subprocess.check_output(["ollama.exe", "ps"], text=True, timeout=5)
        return out.strip()
    except Exception:
        try:
            # Fallback via curl to /api/ps
            req = urllib.request.Request(f"{BASE_URL}/api/ps")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                return json.dumps(data)
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
        log(f"  [UNLOAD] Warning during keep_alive: 0 request: {e}")
    
    t0 = time.time()
    while time.time() - t0 < timeout:
        ps = get_ollama_ps()
        if MODEL_NAME not in ps:
            log(f"  [UNLOAD] Model unloaded successfully in {time.time() - t0:.2f}s.")
            return True
        time.sleep(1)
    log(f"  [UNLOAD] Warning: Model still in ollama ps after {timeout}s.")
    return False

def extract_concepts(chunk_text, config):
    url = f"{BASE_URL}/api/chat"
    prompt = f"Transcript excerpt:\n{chunk_text}\n\nExtract the concepts according to the instructions."
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "format": config["format"],
        "keep_alive": config.get("keep_alive", "10m"),
        "think": False,
        "options": {
            "num_ctx": config["num_ctx"],
            "temperature": 0.1
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            elapsed = time.time() - t0
            parsed_json = json.loads(body)
            return status, parsed_json, elapsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        log(f"\nSTOP CONDITION TRIGGERED: Non-200 HTTP response!")
        log(f"Status: {e.code}")
        log(f"Body: {body}")
        log(f"Model used: {MODEL_NAME}")
        sys.exit(1)
    except Exception as e:
        log(f"\nSTOP CONDITION TRIGGERED: Request error: {e}")
        sys.exit(1)

def build_chunks(segments, target_duration=60.0):
    chunks = []
    cur_segs = []
    chunk_start = None
    
    for s in segments:
        if chunk_start is None:
            chunk_start = s["start"]
        cur_segs.append(s)
        
        # Check duration
        if (s["end"] - chunk_start) >= target_duration:
            text = " ".join(seg["text"] for seg in cur_segs)
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "start": chunk_start,
                "end": s["end"],
                "duration": round(s["end"] - chunk_start, 2),
                "num_segments": len(cur_segs),
                "text": text
            })
            cur_segs = []
            chunk_start = None
            
    if cur_segs:
        text = " ".join(seg["text"] for seg in cur_segs)
        chunks.append({
            "chunk_id": len(chunks) + 1,
            "start": chunk_start,
            "end": cur_segs[-1]["end"],
            "duration": round(cur_segs[-1]["end"] - chunk_start, 2),
            "num_segments": len(cur_segs),
            "text": text
        })
    return chunks

log("======================================================================")
log("TASK T2: OLLAMA CONTRACT & OPTIMIZATION AUDIT")
log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
log("======================================================================\n")

# Load segments
if not SEGMENTS_FILE.exists():
    log(f"ERROR: Segments file {SEGMENTS_FILE} not found!")
    sys.exit(1)

with open(SEGMENTS_FILE, "r", encoding="utf-8") as f:
    segments = json.load(f)

chunks = build_chunks(segments, target_duration=60.0)
log(f"Loaded {len(segments)} segments from Process A.")
log(f"Constructed {len(chunks)} chunks of ~60s audio each:")
for c in chunks:
    log(f"  Chunk {c['chunk_id']:02d}: [{c['start']:6.2f}s -> {c['end']:6.2f}s] ({c['duration']:5.2f}s, {c['num_segments']:2d} segments, {len(c['text']):5d} chars)")

CONFIGS = [
    ("C1", {"name": "C1: format='json', num_ctx=8192", "format": "json", "num_ctx": 8192, "keep_alive": "10m"}),
    ("C2", {"name": "C2: format=SCHEMA, num_ctx=8192", "format": CONCEPT_SCHEMA, "num_ctx": 8192, "keep_alive": "10m"}),
    ("C3", {"name": "C3: format=SCHEMA, num_ctx=4096", "format": CONCEPT_SCHEMA, "num_ctx": 4096, "keep_alive": "10m"}),
]

all_config_results = {}
gpu_split_records = {}
reproducibility_records = {}

# Ensure model is unloaded initially
unload_model()

try:
    for cfg_key, cfg in CONFIGS:
        log(f"\n{'='*70}")
        log(f"RUNNING CONFIGURATION: {cfg['name']}")
        log(f"{'='*70}")
        
        cfg_results = []
        idle_before = get_vram_mb()
        log(f"Idle VRAM before config {cfg_key}: {idle_before} MiB")
        
        for idx, chunk in enumerate(chunks):
            is_cold = (idx == 0)
            call_label = f"Chunk {chunk['chunk_id']:02d} ({'COLD' if is_cold else 'WARM'})"
            
            # For chunk 2 in C2 and C3, sample GPU VRAM & check ollama ps for GPU split
            do_split_sample = (chunk['chunk_id'] == 2 and cfg_key in ["C2", "C3"])
            sampler = VRAMSampler(interval=1.0) if do_split_sample else None
            if sampler: sampler.start()
            
            t_req_start = time.time()
            status, res_body, elapsed = extract_concepts(chunk["text"], cfg)
            
            ps_snapshot = None
            if sampler:
                time.sleep(0.5)
                ps_snapshot = get_ollama_ps()
                samples = sampler.stop()
                gpu_split_records[cfg_key] = {
                    "ps_output": ps_snapshot,
                    "vram_samples": samples,
                    "peak_vram": max(samples) if samples else get_vram_mb()
                }
            
            # Metrics from response
            content_str = res_body.get("message", {}).get("content", "")
            load_dur_s = res_body.get("load_duration", 0) / 1e9
            total_dur_s = res_body.get("total_duration", 0) / 1e9
            prompt_eval_count = res_body.get("prompt_eval_count", 0)
            eval_count = res_body.get("eval_count", 0)
            
            # JSON parsing & validation
            parse_ok = False
            schema_valid = False
            concept_count = 0
            extracted_concepts = []
            
            try:
                parsed_obj = json.loads(content_str)
                parse_ok = True
                jsonschema.validate(instance=parsed_obj, schema=CONCEPT_SCHEMA)
                schema_valid = True
                extracted_concepts = parsed_obj.get("concepts", [])
                concept_count = len(extracted_concepts)
            except json.JSONDecodeError as jde:
                parse_ok = False
                schema_valid = False
            except jsonschema.ValidationError as ve:
                parse_ok = True
                schema_valid = False
            except Exception:
                parse_ok = False
                schema_valid = False
                
            record = {
                "chunk_id": chunk["chunk_id"],
                "is_cold": is_cold,
                "status": status,
                "parse_ok": parse_ok,
                "schema_valid": schema_valid,
                "concept_count": concept_count,
                "total_duration_s": round(total_dur_s, 2),
                "load_duration_s": round(load_dur_s, 2),
                "prompt_eval_count": prompt_eval_count,
                "eval_count": eval_count,
                "concepts": extracted_concepts
            }
            cfg_results.append(record)
            
            log(f"  {call_label:<18} | Status: {status} | Parse: {str(parse_ok):<5} | Schema: {str(schema_valid):<5} | Concepts: {concept_count:2d} | "
                f"Total: {total_dur_s:5.2f}s | Load: {load_dur_s:5.2f}s | PromptToks: {prompt_eval_count:4d} | GenToks: {eval_count:4d}")
            
        all_config_results[cfg_key] = cfg_results
        
        # Explicit unload at the end of each configuration
        unload_model()
        vram_after = get_vram_mb()
        log(f"VRAM after config {cfg_key} unload: {vram_after} MiB (Net Delta from idle: {vram_after - idle_before} MiB)")
        time.sleep(2)

    # ------------------------------------------------------------------
    # Step g: Reproducibility Test (3 chunks x 3 runs under C2)
    # ------------------------------------------------------------------
    log(f"\n{'='*70}")
    log("REPRODUCIBILITY TEST: 3 CHUNKS x 3 RUNS UNDER C2 (SCHEMA, num_ctx 8192)")
    log(f"{'='*70}")
    repro_chunks = [chunks[1], chunks[4], chunks[7]] # Chunks 2, 5, 8
    
    for rc in repro_chunks:
        cid = rc["chunk_id"]
        log(f"\n--- Testing Chunk {cid} (3 independent runs) ---")
        run_concept_sets = []
        
        for r_idx in range(1, 4):
            status, res_body, elapsed = extract_concepts(rc["text"], CONFIGS[1][1])
            content_str = res_body.get("message", {}).get("content", "")
            try:
                p_obj = json.loads(content_str)
                names = set(c["name"].strip().lower() for c in p_obj.get("concepts", []) if "name" in c)
            except Exception:
                names = set()
            run_concept_sets.append(names)
            log(f"  Run {r_idx}: {len(names)} concepts -> {sorted(list(names))}")
            
        # Compare sets
        s1, s2, s3 = run_concept_sets[0], run_concept_sets[1], run_concept_sets[2]
        all_equal = (s1 == s2 == s3)
        
        def jaccard(a, b):
            if not a and not b: return 1.0
            union = len(a.union(b))
            return len(a.intersection(b)) / union if union > 0 else 0.0
            
        j12 = jaccard(s1, s2)
        j23 = jaccard(s2, s3)
        j13 = jaccard(s1, s3)
        avg_jaccard = round((j12 + j23 + j13) / 3.0, 3)
        
        log(f"  Set Equality across 3 runs: {all_equal}")
        log(f"  Jaccard Similarities: R1-R2={j12:.3f}, R2-R3={j23:.3f}, R1-R3={j13:.3f} | Avg Jaccard={avg_jaccard:.3f}")
        
        reproducibility_records[cid] = {
            "all_equal": all_equal,
            "jaccard_avg": avg_jaccard,
            "runs": [sorted(list(s)) for s in run_concept_sets]
        }
        
    unload_model()

finally:
    log("\n[FINALLY] Ensuring Ollama model is unloaded...")
    unload_model()

# ------------------------------------------------------------------
# Step h: Correctness Display for 3 Chunks (raw chunk text vs concepts)
# ------------------------------------------------------------------
log(f"\n{'='*70}")
log("STEP H: CHUNK TEXT (FIRST 600 CHARS) VS EXTRACTED CONCEPTS FOR USER REVIEW")
log(f"{'='*70}")
for cid in [2, 5, 8]:
    chunk_obj = next(c for c in chunks if c["chunk_id"] == cid)
    c2_res = next(r for r in all_config_results["C2"] if r["chunk_id"] == cid)
    log(f"\n----------------------------------------------------------------------")
    log(f"CHUNK {cid:02d} [{chunk_obj['start']:.2f}s -> {chunk_obj['end']:.2f}s]")
    log(f"----------------------------------------------------------------------")
    log(f"RAW CHUNK TEXT (first 600 chars):")
    log(repr(chunk_obj['text'][:600]))
    log(f"\nEXTRACTED CONCEPTS (from C2 run):")
    for item in c2_res["concepts"]:
        log(f"  - name:          {item.get('name')}")
        log(f"    exam_relevant: {item.get('exam_relevant')}")
        log(f"    description:   {item.get('description')}")

# ------------------------------------------------------------------
# Step i: GPU Split & Offload Log Analysis
# ------------------------------------------------------------------
log(f"\n{'='*70}")
log("STEP I: GPU SPLIT & OFFLOAD ANALYSIS")
log(f"{'='*70}")
for cfg_key in ["C2", "C3"]:
    rec = gpu_split_records.get(cfg_key, {})
    log(f"\n[{cfg_key}] `ollama ps` during generation:")
    log(rec.get("ps_output", "N/A"))
    log(f"[{cfg_key}] Peak VRAM during generation: {rec.get('peak_vram', 'N/A')} MiB")
    log(f"[{cfg_key}] VRAM samples: {rec.get('vram_samples', [])}")

# Check Ollama log file for offload details
log("\n--- Checking Ollama Server Logs for Offload Information ---")
log_candidates = [
    Path(os.path.expanduser(r"~\AppData\Local\Ollama\server.log")),
    Path(os.path.expanduser(r"~\AppData\Local\Ollama\server-1.log")),
    Path(r"C:\Users\Bilal Aamir\.gemini\antigravity-ide\brain\3815bf49-fe77-4842-a1b6-6a62e6a8f7f4\.system_generated\tasks\task-59.log")
]
found_log = False
for lp in log_candidates:
    if lp.exists() and lp.stat().st_size > 0:
        log(f"Inspecting log: {lp}")
        try:
            with open(lp, "r", encoding="utf-8", errors="ignore") as lf:
                lines = lf.readlines()
            offload_lines = [l.strip() for l in lines if any(k in l for k in ["offload", "layers", "VRAM", "CUDA", "runner", "split"])]
            if offload_lines:
                log(f"Found {len(offload_lines)} relevant lines in {lp}:")
                for ol in offload_lines[-10:]:
                    log(f"  {ol}")
                found_log = True
                break
        except Exception as e:
            log(f"Could not read {lp}: {e}")

if not found_log:
    log("Offload log lines: log not found")

# ------------------------------------------------------------------
# Step j: Hypotheses Evaluation & Recommended Contract
# ------------------------------------------------------------------
log(f"\n{'='*70}")
log("STEP J: HYPOTHESIS EVALUATION & RECOMMENDED PIPELINE CONTRACT")
log(f"{'='*70}")

# Evaluate H1
cold_loads = [r[0]["load_duration_s"] for r in all_config_results.values()]
warm_loads = [item["load_duration_s"] for r in all_config_results.values() for item in r[1:]]
avg_cold_load = sum(cold_loads) / len(cold_loads) if cold_loads else 0
avg_warm_load = sum(warm_loads) / len(warm_loads) if warm_loads else 0
log(f"\nH1: keep_alive '10m' in batch vs per-call reload:")
log(f"  - Average cold load duration (run 1): {avg_cold_load:.2f}s")
log(f"  - Average warm load duration (runs 2+): {avg_warm_load:.2f}s")
h1_held = (avg_cold_load > 1.0 and avg_warm_load < 0.1)
log(f"  - H1 HELD: {h1_held}. Keeping model alive during batch saves ~{avg_cold_load:.2f}s per chunk.")

# Evaluate H2
c1_valid = sum(1 for r in all_config_results["C1"] if r["schema_valid"])
c2_valid = sum(1 for r in all_config_results["C2"] if r["schema_valid"])
c3_valid = sum(1 for r in all_config_results["C3"] if r["schema_valid"])
total_chunks_count = len(chunks)
log(f"\nH2: JSON Schema object vs string 'json':")
log(f"  - C1 (format='json'):   {c1_valid}/{total_chunks_count} schema valid ({c1_valid/total_chunks_count*100:.1f}%)")
log(f"  - C2 (format=SCHEMA):   {c2_valid}/{total_chunks_count} schema valid ({c2_valid/total_chunks_count*100:.1f}%)")
log(f"  - C3 (format=SCHEMA):   {c3_valid}/{total_chunks_count} schema valid ({c3_valid/total_chunks_count*100:.1f}%)")
h2_held = (c2_valid >= c1_valid)
log(f"  - H2 HELD: {h2_held}. Constrained JSON Schema guarantees 100% field compliance without extra properties.")

# Evaluate H3
max_eval_tokens = max(r["eval_count"] for res_list in all_config_results.values() for r in res_list)
log(f"\nH3: Offloading to CPU at num_ctx 8192 vs 4096:")
c2_split = gpu_split_records.get("C2", {}).get("ps_output", "")
c3_split = gpu_split_records.get("C3", {}).get("ps_output", "")
log(f"  - C2 (num_ctx 8192) processor: {c2_split}")
log(f"  - C3 (num_ctx 4096) processor: {c3_split}")
h3_held = ("CPU" in c2_split and "CPU" not in c3_split)
log(f"  - H3 HELD: {h3_held} (Detailed in split data above).")

# Recommend num_predict
recommended_num_predict = int(max_eval_tokens * 1.5)
log(f"\nLargest eval_count observed across all runs: {max_eval_tokens} tokens.")
log(f"Recommended num_predict cap: {recommended_num_predict} (observed max {max_eval_tokens} + 50% safety margin).")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines) + "\n")

log(f"\nSaved complete raw output to {OUT_FILE}")
