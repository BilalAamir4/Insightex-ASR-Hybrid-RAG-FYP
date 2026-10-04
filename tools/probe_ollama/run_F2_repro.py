import json
import os
import time
import urllib.request
import urllib.error
import subprocess
import sys
from pathlib import Path

BASE_URL = "http://127.0.0.1:11434"
MODEL_NAME = "qwen3.5:latest"
SEGMENTS_FILE = Path(os.environ["INSIGHTEX_DATA"]) / "eval/day04_batch_vs_online/eval/whisper_large_v3_first10min.json"
OUT_FILE = Path(os.environ["INSIGHTEX_DATA"]) / "logs/env_audit/followup2/F2.txt"

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
    "You are an expert computer science educator and educational data extractor. "
    "Analyze the provided transcript segment from an engineering lecture on Machine Learning. "
    "Extract all key technical concepts, terms, methodologies, or paradigms discussed. "
    "For each concept, provide: "
    "1. 'name': Concise canonical technical name in English (e.g. 'Online Learning', 'Batch Gradient Descent'). "
    "2. 'description': Clear summary of how the instructor explains it in this excerpt. "
    "3. 'exam_relevant': Boolean indicating whether this concept is core curricular material likely to appear in an exam. "
    "Output must strictly validate against the provided JSON schema."
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

def extract_concepts(chunk_text):
    url = f"{BASE_URL}/api/chat"
    prompt = f"Transcript excerpt:\n{chunk_text}\n\nExtract the concepts according to the instructions."
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "format": CONCEPT_SCHEMA,
        "keep_alive": "2m",
        "think": False,
        "options": {
            "num_ctx": 8192,
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
    except Exception as e:
        log(f"Request error: {e}")
        raise

def build_chunks(segments, target_duration=60.0):
    chunks = []
    cur_segs = []
    chunk_start = None
    
    for s in segments:
        if chunk_start is None:
            chunk_start = s["start"]
        cur_segs.append(s)
        
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

log("=== TASK F2: CHUNK INDEXING AND REPRODUCIBILITY RE-CHECK ===")
idle_init = get_vram_mb()
log(f"Initial Idle VRAM: {idle_init} MiB")
log(f"Initial ollama ps:\n{get_ollama_ps()}\n")

# Step a: Explanation of indexing
log("--- Step a: Analysis of Chunk Numbering Across Code & Logs ---")
log("In ollama_contract.py:")
log("1. In build_chunks(): 'chunk_id' is assigned as len(chunks) + 1 (1-based: 1, 2, ..., 10).")
log("2. In the per-call loop (Step e): chunks are iterated with 'for idx, chunk in enumerate(chunks)'. 'call_label' prints chunk['chunk_id'] (1-based: Chunk 01 to Chunk 10).")
log("3. In the reproducibility test (Step g): 'repro_chunks = [chunks[1], chunks[4], chunks[7]]'. These 0-based indices map to chunk_ids 2, 5, and 8.")
log("4. In Step h (printed human-review section): 'for cid in [2, 5, 8]: chunk_obj = next(c for c in chunks if c['chunk_id'] == cid)'. This correctly matched chunk_ids 2, 5, and 8.")
log("5. In results/followup/T2.txt: Chunk 02 is [61.34s -> 121.38s], Chunk 05 is [243.32s -> 304.06s], Chunk 08 is [426.16s -> 487.50s].")
log("6. DISCREPANCY ROOT CAUSE: In T2.txt, the actual code ran correctly on chunks 2, 5, and 8. However, in the PREVIOUS ASSISTANT'S CHAT MESSAGE, the text was hallucinated/fabricated (displaying different timestamps like '60.9s -> 119.3s' and completely fabricated concept sets like 'Model Retraining' and 'Machine Learning Software Lifecycle' that did not exist in T2.txt).")

# Step b: Print table of all 10 chunks
log("\n--- Step b: Table of All 10 Chunks ---")
with open(SEGMENTS_FILE, "r", encoding="utf-8") as f:
    segments = json.load(f)

chunks = build_chunks(segments, target_duration=60.0)

log(f"{'1-based ID':<11} | {'0-based Idx':<11} | {'Start':<7} | {'End':<7} | {'Duration':<8} | {'# Segs':<6} | {'First 80 Characters'}")
log("-" * 120)
for idx, c in enumerate(chunks):
    first_80 = c['text'][:80].replace('\n', ' ')
    log(f"{c['chunk_id']:<11} | {idx:<11} | {c['start']:<7.2f} | {c['end']:<7.2f} | {c['duration']:<8.2f} | {c['num_segments']:<6} | {first_80}")

# Target chunks identified by start time
target_starts = [61.34, 243.32, 426.16]
target_chunks = []
for ts in target_starts:
    matched = [c for c in chunks if abs(c["start"] - ts) < 0.5]
    if not matched:
        log(f"ERROR: Could not find chunk starting near {ts}s!")
        sys.exit(1)
    target_chunks.append(matched[0])

log("\nIdentified target chunks for reproducibility test by start time:")
for tc in target_chunks:
    log(f"  Chunk ID {tc['chunk_id']} (Start: {tc['start']:.2f}s, End: {tc['end']:.2f}s)")

# Step c: Re-run reproducibility test
log("\n--- Step c: Re-running Reproducibility Test (C2: JSON Schema, num_ctx 8192, temp 0.1, keep_alive 2m) ---")
repro_results = {}

try:
    for tc in target_chunks:
        cid = tc["chunk_id"]
        start_end = f"[{tc['start']:.2f}s -> {tc['end']:.2f}s]"
        log(f"\n=======================================================")
        log(f"Testing Chunk {cid} {start_end} (3 independent runs)")
        log(f"=======================================================")
        
        runs_data = []
        for r_num in range(1, 4):
            t_start = time.time()
            status, res_body, elapsed = extract_concepts(tc["text"])
            content_str = res_body.get("message", {}).get("content", "")
            parsed_obj = json.loads(content_str)
            raw_concepts = parsed_obj.get("concepts", [])
            concept_names = [c["name"].strip() for c in raw_concepts if "name" in c]
            name_set = set(c["name"].strip().lower() for c in raw_concepts if "name" in c)
            
            runs_data.append({
                "run": r_num,
                "elapsed": round(elapsed, 2),
                "concept_names": concept_names,
                "name_set": name_set,
                "raw_concepts": raw_concepts
            })
            log(f"  Run {r_num} ({elapsed:.2f}s): {len(concept_names)} concepts -> {concept_names}")
            
        s1 = runs_data[0]["name_set"]
        s2 = runs_data[1]["name_set"]
        s3 = runs_data[2]["name_set"]
        
        def calc_jaccard(a, b):
            if not a and not b:
                return 1.0, 0, 0
            inter = len(a.intersection(b))
            union = len(a.union(b))
            return (inter / union if union > 0 else 0.0), inter, union

        j12, i12, u12 = calc_jaccard(s1, s2)
        j23, i23, u23 = calc_jaccard(s2, s3)
        j13, i13, u13 = calc_jaccard(s1, s3)
        all_equal = (s1 == s2 == s3)
        avg_j = (j12 + j23 + j13) / 3.0
        
        log(f"\n  [Metrics for Chunk {cid} {start_end}]")
        log(f"  Set Equality across 3 runs: {all_equal}")
        log(f"  Pairwise Jaccard calculations:")
        log(f"    R1 vs R2: intersection={i12}, union={u12} -> Jaccard = {j12:.4f}")
        log(f"    R2 vs R3: intersection={i23}, union={u23} -> Jaccard = {j23:.4f}")
        log(f"    R1 vs R3: intersection={i13}, union={u13} -> Jaccard = {j13:.4f}")
        log(f"    Mean Jaccard across 3 pairs: {avg_j:.4f}")
        
        repro_results[cid] = {
            "chunk": tc,
            "runs": runs_data,
            "all_equal": all_equal,
            "j12": j12, "j23": j23, "j13": j13, "avg_j": avg_j
        }

finally:
    log("\n[FINALLY BLOCK] Unloading model...")
    unload_model()
    time.sleep(2)
    ps_final = get_ollama_ps()
    vram_final = get_vram_mb()
    log(f"Post-unload ollama ps:\n{ps_final}")
    log(f"Post-unload VRAM: {vram_final} MiB (Initial idle: {idle_init} MiB, Delta: {vram_final - idle_init} MiB)")

# Step d: Print first 600 chars of chunk text beside run 1 concepts
log("\n--- Step d: Chunk Text (First 600 Chars) Beside Run 1 Concepts ---")
for tc in target_chunks:
    cid = tc["chunk_id"]
    start_end = f"[{tc['start']:.2f}s -> {tc['end']:.2f}s]"
    r1_concepts = repro_results[cid]["runs"][0]["raw_concepts"]
    log(f"\n{'='*80}")
    log(f"CHUNK {cid:02d} {start_end}")
    log(f"{'='*80}")
    log("RAW CHUNK TRANSCRIPT (first 600 chars):")
    log(tc['text'][:600])
    log(f"\nRUN 1 EXTRACTED CONCEPTS ({len(r1_concepts)} items):")
    for item in r1_concepts:
        log(f"  - Name:          {item.get('name')}")
        log(f"    Exam Relevant: {item.get('exam_relevant')}")
        log(f"    Description:   {item.get('description')}")

# Step e: Correct earlier numbers
log("\n--- Step e: Correction of Earlier Reported Numbers ---")
log("Earlier (faulty chat message) reported:")
log("  Chunk 2: Set equality=True, Jaccard=1.000")
log("  Chunk 5: Set equality=False, Jaccard=0.556 (with fabricated concept sets {A,B,C} vs {A,B,C,D})")
log("  Chunk 8: Set equality=False, Jaccard=0.667")
log("\nActual measurements in this run:")
for tc in target_chunks:
    cid = tc["chunk_id"]
    res = repro_results[cid]
    log(f"  Chunk {cid} [{tc['start']:.2f}s -> {tc['end']:.2f}s]:")
    log(f"    Set equality: {res['all_equal']}")
    log(f"    Pairwise Jaccards: R1-R2={res['j12']:.4f}, R2-R3={res['j23']:.4f}, R1-R3={res['j13']:.4f}")
    log(f"    Mean Jaccard: {res['avg_j']:.4f}")

# Save to F2.txt
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")
log(f"\nRaw output written to {OUT_FILE}")
