#!/usr/bin/env python3
"""
Item 3: Ollama Call Contract & API Verification.
Tests:
- /api/tags
- Minimal generate and chat calls
- Matrix: {/api/generate, /api/chat} x {think: true, think: false} with format="json"
- Realistic concept-extraction on ~1,500 token Roman-Urdu/English text (cold vs warm)
- VRAM peak monitoring and baseline verification
"""
import os
import sys
import time
import json
import threading
import subprocess
import urllib.request
import urllib.error

BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen3.5:latest"
NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"
ROMAN_TEXT_FILE = "/mnt/e/FYP/data/day04_batch_vs_online/eval/manual_roman.txt"

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
    def __init__(self, interval=0.2):
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
        return self.baseline_vram, self.peak_vram

def http_post(endpoint, payload, timeout=300):
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            elapsed = time.time() - t0
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body}
            return status, parsed, elapsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, {"error": body}, time.time() - t0
    except Exception as e:
        return 0, {"error": str(e)}, time.time() - t0

def unload_model():
    """Ensure Ollama model is unloaded from VRAM."""
    http_post("/api/generate", {"model": MODEL_NAME, "keep_alive": 0})
    time.sleep(2)

def test_connectivity():
    print("="*70)
    print("1. TAGS & CONNECTIVITY TEST")
    print("="*70)
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name") for m in body.get("models", [])]
            print(f"Status: {status}")
            print(f"Installed models: {models}")
            if MODEL_NAME in models:
                print(f"CONFIRMED: Model '{MODEL_NAME}' is present.")
            else:
                print(f"WARNING: Model '{MODEL_NAME}' NOT in tags!")
    except Exception as e:
        print(f"FAILED to reach {BASE_URL}/api/tags: {e}")

def test_matrix():
    print("\n" + "="*70)
    print("2. MATRIX: {generate, chat} x {think true, think false} x format=json")
    print("="*70)
    matrix_results = []
    cases = [
        ("/api/generate", True),
        ("/api/generate", False),
        ("/api/chat", True),
        ("/api/chat", False),
    ]
    prompt_text = "Return a JSON object with key 'status' and value 'ok', and key 'count' and value 42."

    for endpoint, think in cases:
        label = f"{endpoint} | think={think}"
        print(f"\n--- Testing: {label} ---")
        if endpoint == "/api/generate":
            payload = {
                "model": MODEL_NAME,
                "prompt": prompt_text,
                "stream": False,
                "format": "json",
                "keep_alive": 0,
                "think": think,
                "options": {"num_ctx": 4096, "temperature": 0.0}
            }
        else:
            payload = {
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt_text}],
                "stream": False,
                "format": "json",
                "keep_alive": 0,
                "think": think,
                "options": {"num_ctx": 4096, "temperature": 0.0}
            }

        status, body, elapsed = http_post(endpoint, payload)
        raw_response = body.get("response", "")
        msg = body.get("message", {})
        raw_msg_content = msg.get("content", "")
        # Check thinking field in top level or in message
        raw_thinking = body.get("thinking", "") or msg.get("thinking", "")

        # Try to parse JSON from content/response
        content_to_parse = raw_response if endpoint == "/api/generate" else raw_msg_content
        json_parses = False
        parsed_obj = None
        try:
            if content_to_parse.strip():
                parsed_obj = json.loads(content_to_parse.strip())
                json_parses = True
        except Exception:
            json_parses = False

        print(f"HTTP Status: {status} (elapsed: {elapsed:.2f}s)")
        if endpoint == "/api/generate":
            print(f"raw `response` (first 300 chars): {repr(raw_response[:300])}")
        else:
            print(f"raw `message.content` (first 300 chars): {repr(raw_msg_content[:300])}")
        print(f"raw `thinking` (first 300 chars): {repr(raw_thinking[:300])}")
        print(f"JSON parses: {json_parses} -> {parsed_obj}")

        matrix_results.append({
            "endpoint": endpoint,
            "think": think,
            "status": status,
            "elapsed_s": round(elapsed, 2),
            "response_snippet": raw_response[:300],
            "message_content_snippet": raw_msg_content[:300],
            "thinking_snippet": raw_thinking[:300],
            "json_parses": json_parses,
        })
        time.sleep(1)

    return matrix_results

def test_concept_extraction():
    print("\n" + "="*70)
    print("3. REALISTIC CONCEPT EXTRACTION TEST (~1,500 TOKENS)")
    print("="*70)
    if not os.path.exists(ROMAN_TEXT_FILE):
        print(f"ERROR: {ROMAN_TEXT_FILE} does not exist!")
        return {}

    with open(ROMAN_TEXT_FILE, "r", encoding="utf-8") as f:
        full_text = f.read()

    # Take first ~1,500 tokens (~6,500 characters)
    lecture_chunk = full_text[:6500]
    word_count = len(lecture_chunk.split())
    char_count = len(lecture_chunk)
    print(f"Input text: {char_count} chars, ~{word_count} words (~{int(word_count * 1.3)} tokens)")

    system_instruction = (
        "You are an expert AI educator analyzing bilingual lecture transcripts (Urdu/English code-switched). "
        "Extract the core technical concepts mentioned in the text. "
        "Return ONLY a JSON object with a single key 'concepts' containing a list of objects. "
        "Each object must have: 'name' (string), 'description' (string in English), 'exam_relevant' (boolean)."
    )

    prompt = f"Transcript excerpt:\n{lecture_chunk}\n\nExtract the concepts according to the instructions."

    # Cold run: first unload
    print("\n--- Unloading model to ensure cold start ---")
    unload_model()
    idle_vram = get_vram_mb()
    print(f"Idle VRAM before cold run: {idle_vram} MiB")

    # Use /api/chat with think=False, format="json", num_ctx=8192
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "format": "json",
        "keep_alive": "5m",  # keep loaded for warm repeat
        "think": False,
        "options": {
            "num_ctx": 8192,
            "temperature": 0.1
        }
    }

    # Run 1: Cold (loads model + infers)
    print("\n>>> Launching Run 1 (Cold model load + inference)...")
    sampler1 = VRAMSampler(interval=0.2)
    sampler1.start()
    status1, body1, elapsed1 = http_post("/api/chat", payload)
    base1, peak1 = sampler1.stop()

    content1 = body1.get("message", {}).get("content", "")
    load_dur1 = body1.get("load_duration", 0) / 1e9
    eval_dur1 = body1.get("eval_duration", 0) / 1e9
    prompt_eval_dur1 = body1.get("prompt_eval_duration", 0) / 1e9
    prompt_tokens1 = body1.get("prompt_eval_count", 0)
    eval_tokens1 = body1.get("eval_count", 0)

    print(f"Run 1 (Cold) Elapsed: {elapsed1:.2f}s")
    print(f"  - Model load duration: {load_dur1:.2f}s")
    print(f"  - Prompt eval duration ({prompt_tokens1} tokens): {prompt_eval_dur1:.2f}s")
    print(f"  - Generation duration ({eval_tokens1} tokens): {eval_dur1:.2f}s")
    print(f"  - Peak VRAM during generation: {peak1} MiB (baseline: {base1} MiB, delta: +{peak1 - base1} MiB)")

    json1_parses = False
    matches_schema1 = False
    parsed1 = None
    try:
        parsed1 = json.loads(content1.strip())
        json1_parses = True
        if isinstance(parsed1, dict) and "concepts" in parsed1 and isinstance(parsed1["concepts"], list):
            valid = True
            for item in parsed1["concepts"]:
                if not ("name" in item and "exam_relevant" in item and isinstance(item["exam_relevant"], bool)):
                    valid = False
                    break
            matches_schema1 = valid
    except Exception as e:
        print(f"JSON Parse Error: {e}")

    print(f"JSON parses: {json1_parses}")
    print(f"Matches schema (list with exam_relevant boolean): {matches_schema1}")
    if parsed1 and "concepts" in parsed1:
        print(f"Extracted {len(parsed1['concepts'])} concepts:")
        for c in parsed1["concepts"][:5]:
            print(f"  - {c.get('name')}: exam_relevant={c.get('exam_relevant')} ({c.get('description')[:60]}...)")

    time.sleep(2)

    # Run 2: Warm repeat
    print("\n>>> Launching Run 2 (Warm repeat with model already resident)...")
    payload["keep_alive"] = 0  # Unload immediately after warm run
    sampler2 = VRAMSampler(interval=0.2)
    sampler2.start()
    status2, body2, elapsed2 = http_post("/api/chat", payload)
    base2, peak2 = sampler2.stop()

    content2 = body2.get("message", {}).get("content", "")
    load_dur2 = body2.get("load_duration", 0) / 1e9
    eval_dur2 = body2.get("eval_duration", 0) / 1e9
    prompt_eval_dur2 = body2.get("prompt_eval_duration", 0) / 1e9
    prompt_tokens2 = body2.get("prompt_eval_count", 0)
    eval_tokens2 = body2.get("eval_count", 0)

    print(f"Run 2 (Warm) Elapsed: {elapsed2:.2f}s")
    print(f"  - Model load duration: {load_dur2:.2f}s")
    print(f"  - Prompt eval duration ({prompt_tokens2} tokens): {prompt_eval_dur2:.2f}s")
    print(f"  - Generation duration ({eval_tokens2} tokens): {eval_dur2:.2f}s")
    print(f"  - Peak VRAM during generation: {peak2} MiB (baseline: {base2} MiB)")

    json2_parses = False
    matches_schema2 = False
    try:
        parsed2 = json.loads(content2.strip())
        json2_parses = True
        if isinstance(parsed2, dict) and "concepts" in parsed2 and isinstance(parsed2["concepts"], list):
            valid = True
            for item in parsed2["concepts"]:
                if not ("name" in item and "exam_relevant" in item and isinstance(item["exam_relevant"], bool)):
                    valid = False
                    break
            matches_schema2 = valid
    except Exception as e:
        print(f"JSON Parse Error: {e}")

    print(f"JSON parses: {json2_parses}")
    print(f"Matches schema: {matches_schema2}")

    # Ensure unloaded
    print("\n--- Verifying VRAM return to baseline with keep_alive=0 ---")
    unload_model()
    time.sleep(3)
    final_vram = get_vram_mb()
    print(f"VRAM after unload: {final_vram} MiB (initial idle: {idle_vram} MiB)")

    return {
        "cold": {
            "elapsed_s": round(elapsed1, 2),
            "load_duration_s": round(load_dur1, 2),
            "prompt_eval_duration_s": round(prompt_eval_dur1, 2),
            "eval_duration_s": round(eval_dur1, 2),
            "peak_vram_mb": peak1,
            "baseline_vram_mb": base1,
            "json_parses": json1_parses,
            "matches_schema": matches_schema1,
            "concept_count": len(parsed1.get("concepts", [])) if parsed1 else 0
        },
        "warm": {
            "elapsed_s": round(elapsed2, 2),
            "load_duration_s": round(load_dur2, 2),
            "prompt_eval_duration_s": round(prompt_eval_dur2, 2),
            "eval_duration_s": round(eval_dur2, 2),
            "peak_vram_mb": peak2,
            "baseline_vram_mb": base2,
            "json_parses": json2_parses,
            "matches_schema": matches_schema2,
        },
        "initial_idle_vram": idle_vram,
        "final_vram": final_vram
    }

if __name__ == "__main__":
    test_connectivity()
    mat = test_matrix()
    res = test_concept_extraction()
    print("\n" + "="*70)
    print("ALL TESTS COMPLETED.")
    print("="*70)
