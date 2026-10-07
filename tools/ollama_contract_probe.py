"""Worst-case VRAM / context probe for the Ollama call contract (qwen3.5:latest).

Standalone (does not import from backend/). Builds one concept-extraction prompt
(system prompt + 5 consecutive 30 s windows of the Day 4 transcript + 2 placeholder
ML textbook chunks), runs it at num_ctx 4096 and 8192, and records baseline VRAM,
peak VRAM, the model's own share (peak - baseline), the PROCESSOR column of
`ollama ps`, prompt_eval_count, tokens/sec and JSON validity.

Run: bash scripts/run_in_env.sh python tools/ollama_contract_probe.py
Padded mode: ... probe.py --run 8192:7000 --run 16384:14000   (num_ctx:target prompt tokens; appends to the measurements file)
Needs Ollama up and nothing else on the GPU. Writes docs/measurements/<date>_ollama_contract.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import httpx

MODEL = "qwen3.5:latest"
BASE = os.environ["OLLAMA_BASE_URL"].rstrip("/")
DATA = Path(os.environ["INSIGHTEX_DATA"])
TRANSCRIPT = DATA / "eval/day04_batch_vs_online/eval/whisper_large_v3_first10min.json"
REPO = Path(__file__).resolve().parents[1]
CTX_SIZES = [4096, 8192]
WINDOW_S = 30
NUM_PREDICT = 1024
N_WINDOWS = 5

SYSTEM_PROMPT = (
    "You are a teaching assistant extracting study concepts from a lecture. You are given a "
    "transcript excerpt (spoken, mixed Urdu/English) and two textbook passages. List the key "
    "machine-learning concepts a student must know. For every concept give: label (a short "
    "canonical English name), importance (integer 1 to 5, 5 = most exam-relevant) and "
    "evidence_quote (an exact short quote copied from the transcript or textbook text that "
    "supports it). Reply with JSON only, in the form "
    '{"concepts":[{"label":str,"importance":int,"evidence_quote":str}]}. '
    "List at most 15 concepts, the most important first. Do not invent concepts that the text does not support."
)

# Placeholder textbook text: the real textbook is not chosen yet (M0b).
TEXTBOOK_CHUNKS = [
    """Batch learning and online learning describe two different ways a system can be trained. In batch learning, also called offline learning, the system is incapable of learning incrementally: it must be trained using all the available data. This will generally take a lot of time and computing resources, so it is typically done offline. First the system is trained, and then it is launched into production and runs without learning anymore; it just applies what it has learned. If you want a batch learning system to know about new data, such as a new type of spam, you need to train a new version of the system from scratch on the full dataset, then stop the old system and replace it with the new one. Fortunately, the whole process of training, evaluating and launching a machine learning system can be automated fairly easily, so even a batch learning system can adapt to change. Simply update the data and train a new version as often as needed. This solution is simple and often works fine, but training on the full set of data can take many hours, so you would typically train a new system only every twenty-four hours or even just weekly. If your system needs to adapt to rapidly changing data, for example to predict stock prices, then you need a more reactive solution. Also, training on the full set of data requires a lot of computing resources, including CPU, memory space, disk space, disk input and output, and network input and output. If you have a lot of data and you automate your system to train from scratch every day, it will end up costing you a lot of money. If the amount of data is huge, it may even be impossible to use a batch learning algorithm. Finally, if your system needs to be able to learn autonomously and it has limited resources, for example a smartphone application or a rover on Mars, then carrying around large amounts of training data and taking up a lot of resources to train for hours every day is a showstopper.""",
    """In online learning, you train the system incrementally by feeding it data instances sequentially, either individually or in small groups called mini-batches. Each learning step is fast and cheap, so the system can learn about new data on the fly, as it arrives. Online learning is great for systems that receive data as a continuous flow, such as stock prices, and need to adapt to change rapidly or autonomously. It is also a good option if you have limited computing resources: once an online learning system has learned about new data instances, it does not need them anymore, so you can discard them unless you want to roll back to a previous state and replay the data. This can save a huge amount of space. Online learning algorithms can also be used to train systems on huge datasets that cannot fit in one machine's main memory, which is called out-of-core learning. The algorithm loads part of the data, runs a training step on that data, and repeats the process until it has run on all of the data. One important parameter of online learning systems is how fast they should adapt to changing data, which is called the learning rate. If you set a high learning rate, then your system will rapidly adapt to new data, but it will also tend to quickly forget the old data. Conversely, if you set a low learning rate, the system will have more inertia; that is, it will learn more slowly, but it will also be less sensitive to noise in the new data or to sequences of nonrepresentative data points, which are outliers. A big challenge with online learning is that if bad data is fed to the system, the system's performance will gradually decline. If it is a live system, your clients will notice. For example, bad data could come from a malfunctioning sensor on a robot, or from someone spamming a search engine to try to rank high in search results. To reduce this risk, you need to monitor your system closely and promptly switch learning off, and possibly revert to a previously working state, if you detect a drop in performance. You may also want to monitor the input data and react to abnormal data, for example using an anomaly detection algorithm.""",
]

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "importance": {"type": "integer"},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["label", "importance", "evidence_quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["concepts"],
    "additionalProperties": False,
}


def smi_used_mib() -> int:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True
    )
    return int(out.strip().splitlines()[0])


class VramSampler(threading.Thread):
    def __init__(self, interval: float = 0.2):
        super().__init__(daemon=True)
        self.interval, self.peak, self.samples, self._stop_evt = interval, 0, 0, threading.Event()

    def run(self):
        while not self._stop_evt.is_set():
            try:
                self.peak = max(self.peak, smi_used_mib())
                self.samples += 1
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self):
        self._stop_evt.set()
        self.join()


def settle_baseline(timeout: float = 30.0) -> int:
    """VRAM once stable (two consecutive reads within 20 MiB, 1 s apart)."""
    prev, deadline = smi_used_mib(), time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1.0)
        cur = smi_used_mib()
        if abs(cur - prev) <= 20:
            return cur
        prev = cur
    return cur


def ollama_ps_processor() -> tuple[str, dict | None]:
    """PROCESSOR column. Uses the real `ollama ps` (Windows exe via powershell) when available."""
    api = httpx.get(f"{BASE}/api/ps", timeout=10).json().get("models", [])
    entry = next((m for m in api if m["name"] == MODEL), None)
    cli = None
    try:
        cli = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "ollama ps"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception:
        pass
    col = None
    if cli:
        m = re.search(r"(\d+%\s*(?:GPU|CPU)(?:/\d+%\s*(?:GPU|CPU))?|\d+%/\d+%\s*CPU/GPU)", cli)
        col = m.group(1) if m else None
    if col is None and entry:
        pct = 100 * entry["size_vram"] / entry["size"] if entry["size"] else 0
        col = f"{pct:.0f}% GPU (from /api/ps size_vram/size)" if pct >= 99.5 else f"{pct:.0f}% GPU / {100 - pct:.0f}% CPU (from /api/ps)"
    return col or "model not resident", entry


def unload() -> bool:
    httpx.post(f"{BASE}/api/generate", json={"model": MODEL, "keep_alive": 0}, timeout=60)
    for _ in range(60):
        if not any(m["name"] == MODEL for m in httpx.get(f"{BASE}/api/ps", timeout=10).json().get("models", [])):
            return True
        time.sleep(0.5)
    return False


def build_prompt() -> tuple[list[dict], str, dict]:
    segs = json.loads(TRANSCRIPT.read_text())
    by_win: dict[int, list[str]] = {}
    for s in segs:
        by_win.setdefault(int(s["start"] // WINDOW_S), []).append(s["text"].strip())
    wins = sorted(by_win)
    # worst case: the 5 consecutive windows with the most characters
    best = max(
        (w for w in wins if all((w + i) in by_win for i in range(N_WINDOWS))),
        key=lambda w: sum(len(" ".join(by_win[w + i])) for i in range(N_WINDOWS)),
    )
    parts = [f"[{(best + i) * WINDOW_S}s-{(best + i + 1) * WINDOW_S}s] " + " ".join(by_win[best + i]) for i in range(N_WINDOWS)]
    transcript_txt = "\n".join(parts)
    user = (
        "TRANSCRIPT (5 consecutive 30 s windows):\n" + transcript_txt
        + "\n\nTEXTBOOK PASSAGE 1:\n" + TEXTBOOK_CHUNKS[0]
        + "\n\nTEXTBOOK PASSAGE 2:\n" + TEXTBOOK_CHUNKS[1]
        + "\n\nExtract the concepts as JSON."
    )
    meta = {
        "first_window_start_s": best * WINDOW_S,
        "transcript_chars": len(transcript_txt),
        "transcript_words": len(transcript_txt.split()),
        "textbook_words": [len(c.split()) for c in TEXTBOOK_CHUNKS],
    }
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}], transcript_txt + " ".join(TEXTBOOK_CHUNKS), meta


def norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def run_one(messages, source_text, num_ctx, baseline) -> dict:
    sampler = VramSampler()
    body = {
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "format": RESPONSE_SCHEMA, "keep_alive": "10m",
        "options": {"num_ctx": num_ctx, "temperature": 0, "seed": 42, "num_predict": NUM_PREDICT},
    }
    sampler.start()
    t0 = time.monotonic()
    try:
        data = httpx.post(f"{BASE}/api/chat", json=body, timeout=900).json()
    finally:
        wall = time.monotonic() - t0
        time.sleep(0.5)
        processor, entry = ollama_ps_processor()
        sampler.stop()
    content = data.get("message", {}).get("content", "")
    valid, sensible, notes = False, None, []
    try:
        obj = json.loads(content)
        concepts = obj["concepts"]
        assert isinstance(concepts, list)
        for c in concepts:
            assert set(c) == {"label", "importance", "evidence_quote"}
            assert isinstance(c["label"], str) and isinstance(c["importance"], int) and isinstance(c["evidence_quote"], str)
        valid = True
        src = norm(source_text)
        grounded = sum(1 for c in concepts if c["evidence_quote"].strip() and norm(c["evidence_quote"]) in src)
        sensible = {"n_concepts": len(concepts), "quotes_found_verbatim": grounded,
                    "importance_in_1_5": all(1 <= c["importance"] <= 5 for c in concepts),
                    "labels": [c["label"] for c in concepts][:10]}
    except Exception as e:
        notes.append(f"invalid JSON/schema: {e!r}")
    eval_s = data.get("eval_duration", 0) / 1e9
    return {
        "num_ctx": num_ctx, "baseline_mib": baseline, "peak_mib": sampler.peak,
        "model_share_mib": sampler.peak - baseline, "vram_samples": sampler.samples,
        "free_at_peak_mib": 8192 - sampler.peak,
        "processor": processor,
        "ps_size_bytes": entry and entry["size"], "ps_size_vram_bytes": entry and entry["size_vram"],
        "ps_context_length": entry and entry.get("context_length"),
        "prompt_eval_count": data.get("prompt_eval_count"), "eval_count": data.get("eval_count"),
        "tokens_per_sec": round(data.get("eval_count", 0) / eval_s, 1) if eval_s else None,
        "load_s": round(data.get("load_duration", 0) / 1e9, 2), "wall_s": round(wall, 1),
        "done_reason": data.get("done_reason"),
        "thinking_present": bool(data.get("message", {}).get("thinking")),
        "json_valid": valid, "sensible": sensible, "notes": notes,
    }


TOPICS = [
    "linear regression and the normal equation", "gradient descent and the learning rate", "logistic regression and the sigmoid function",
    "overfitting, underfitting and the bias-variance tradeoff", "regularisation with L1 and L2 penalties", "cross-validation and model selection",
    "decision trees and information gain", "random forests and bagging", "gradient boosting", "support vector machines and the kernel trick",
    "k-nearest neighbours and the curse of dimensionality", "k-means clustering", "principal component analysis", "naive Bayes classifiers",
    "feature scaling and normalisation", "handling missing data and outliers", "evaluation metrics: precision, recall and F1",
    "the confusion matrix and ROC curves", "supervised versus unsupervised versus reinforcement learning", "training, validation and test sets and data leakage",
    "neural networks and backpropagation", "activation functions", "stochastic and mini-batch gradient descent", "model drift and monitoring in production",
    "instance-based versus model-based learning",
]
CHUNKS_CACHE = DATA / "eval/probe_textbook_chunks.json"


def extra_chunks() -> list[str]:
    """Textbook-style passages for padding. Generated once by qwen3.5 (placeholder text; the real textbook is not chosen yet)."""
    if CHUNKS_CACHE.exists():
        return json.loads(CHUNKS_CACHE.read_text())["chunks"]
    chunks = []
    for i, topic in enumerate(TOPICS):
        body = {"model": MODEL, "stream": False, "think": False, "keep_alive": "10m",
                "messages": [{"role": "user", "content": f"Write a passage of about 400 words in the style of an introductory machine learning textbook on: {topic}. Plain connected prose in one or two paragraphs; no headings, no lists, no markdown, no equations."}],
                "options": {"num_ctx": 4096, "temperature": 0.7, "seed": 100 + i, "num_predict": 700}}
        chunks.append(httpx.post(f"{BASE}/api/chat", json=body, timeout=600).json()["message"]["content"].strip())
        print(f"generated chunk {i + 1}/{len(TOPICS)}: {len(chunks[-1].split())} words", flush=True)
    unload()
    CHUNKS_CACHE.write_text(json.dumps({"note": "LLM-generated placeholder textbook text for probe padding", "model": MODEL, "topics": TOPICS, "chunks": chunks}, indent=1))
    return chunks


def padded_messages(chunks: list[str], nonce: str = "") -> tuple[list[dict], str]:
    segs = json.loads(TRANSCRIPT.read_text())
    by_win: dict[int, list[str]] = {}
    for s in segs:
        by_win.setdefault(int(s["start"] // WINDOW_S), []).append(s["text"].strip())
    transcript_txt = "\n".join(f"[{w * WINDOW_S}s-{(w + 1) * WINDOW_S}s] " + " ".join(by_win[w]) for w in sorted(by_win))
    texts = TEXTBOOK_CHUNKS + chunks
    user = ("TRANSCRIPT (all consecutive 30 s windows of the first 10 minutes):\n" + transcript_txt
            + "".join(f"\n\nTEXTBOOK PASSAGE {i + 1}:\n{c}" for i, c in enumerate(texts)) + "\n\nExtract the concepts as JSON.")
    sysmsg = (f"[run {nonce}] " if nonce else "") + SYSTEM_PROMPT
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}], transcript_txt + " ".join(texts)


def count_tokens(chunks, num_ctx, nonce) -> int:
    """prompt_eval_count of a num_predict=1 call. A fresh nonce at the very start defeats Ollama's prefix cache."""
    msgs, _ = padded_messages(chunks, nonce)
    body = {"model": MODEL, "messages": msgs, "stream": False, "think": False, "keep_alive": "10m",
            "options": {"num_ctx": num_ctx, "temperature": 0, "seed": 42, "num_predict": 1}}
    return httpx.post(f"{BASE}/api/chat", json=body, timeout=900).json()["prompt_eval_count"]


def fit_chunks(pool: list[str], num_ctx: int, target: int, tol: float = 0.03) -> tuple[list[str], int]:
    """Whole passages from the pool, with the last one trimmed (at a sentence end) to land within tol of target tokens."""
    n = 0
    chunks: list[str] = []
    cur = count_tokens(chunks, num_ctx, f"c{n}")
    per_word = None
    for _ in range(12):
        if abs(cur - target) <= tol * target:
            break
        if per_word is None:
            words = len(padded_messages(chunks)[0][1]["content"].split())
            per_word = cur / words
        need_words = int((target - cur) / per_word)
        if need_words <= 0:
            # overshoot: trim the last chunk
            last = chunks[-1].split()
            keep = max(0, len(last) + need_words)
            text = " ".join(last[:keep])
            text = text[: text.rfind(".") + 1] if "." in text else text
            chunks[-1] = text
        else:
            # add as many whole passages as fit in need_words, then a trimmed one for the remainder
            while need_words > 0 and len(chunks) < len(pool):
                words_next = pool[len(chunks)].split()
                if need_words >= len(words_next):
                    chunks.append(pool[len(chunks)])
                    need_words -= len(words_next)
                else:
                    cut = " ".join(words_next[:need_words])
                    chunks.append(cut[: cut.rfind(".") + 1] if "." in cut else cut)
                    need_words = 0
            if need_words > 0:
                raise SystemExit(f"chunk pool exhausted at {cur} tokens (target {target})")
        n += 1
        cur = count_tokens(chunks, num_ctx, f"c{n}")
    if abs(cur - target) > tol * target:
        raise SystemExit(f"could not fit prompt to {target} tokens (got {cur})")
    return chunks, cur


def padded_main(runs: list[tuple[int, int]]):
    if httpx.get(f"{BASE}/api/ps", timeout=10).json().get("models"):
        raise SystemExit("A model is already loaded. Unload it first.")
    pool = extra_chunks()
    for i, (num_ctx, target) in enumerate(runs):
        chunks, calibrated = fit_chunks(pool, num_ctx, target)
        if not unload():
            raise SystemExit("could not unload after calibration")
        time.sleep(2)
        baseline = settle_baseline()
        msgs, source_text = padded_messages(chunks)  # no nonce in the measured run
        r = run_one(msgs, source_text, num_ctx, baseline)
        r.update({"target_tokens": target, "calibrated_tokens": calibrated, "n_extra_chunks": len(chunks)})
        pe = r["prompt_eval_count"] or 0
        r["prompt_intact"] = abs(pe - calibrated) <= 16 and pe < num_ctx
        r["unloaded"] = unload()
        time.sleep(2)
        r["after_unload_mib"] = settle_baseline()
        r["returned_to_baseline"] = abs(r["after_unload_mib"] - baseline) <= 200
        print(json.dumps(r, indent=1), flush=True)
        write_padded_run(r, first=(i == 0))


def write_padded_run(r, first: bool):
    """Append one run to the measurements file right away, so a later failure cannot lose it."""
    out = REPO / "docs/measurements" / f"{dt.date.today().isoformat()}_ollama_contract.md"
    L = [""]
    if first:
        L += [f"## Padded-prompt runs, {dt.datetime.now():%H:%M} (near-limit context, `num_predict` {NUM_PREDICT}, at most 15 concepts)", "",
              "Prompt: system prompt + all 20 consecutive 30 s windows of the first 10 min of the Day 4 transcript + the 2 placeholder chunks above + additional textbook-style passages, "
              "added until `prompt_eval_count` reached the target (last passage trimmed at a sentence end). The extra passages are LLM-generated placeholder text (qwen3.5, 25 topics, cached at "
              "`$INSIGHTEX_DATA/eval/probe_textbook_chunks.json`), not filler repetition and not the chosen textbook. "
              "Each measured run starts from a freshly loaded model (calibration was unloaded first); calibration used `num_predict: 1` with a unique nonce so the prefix cache could not understate the count. "
              "Each run is appended as soon as it finishes. Single run per setting.", "",
              "| num_ctx | target tokens | prompt_eval_count (measured run) | intact? | baseline MiB | peak MiB | model share MiB | free at peak MiB | PROCESSOR | out tokens | tok/s | done_reason | JSON valid | after unload MiB |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    L.append(f"| {r['num_ctx']} | {r['target_tokens']} | {r['prompt_eval_count']} (calibrated {r['calibrated_tokens']}) | {'yes' if r['prompt_intact'] else 'NO'} | {r['baseline_mib']} | {r['peak_mib']} | {r['model_share_mib']} | {r['free_at_peak_mib']} | {r['processor']} | {r['eval_count']} | {r['tokens_per_sec']} | {r['done_reason']} | {r['json_valid']} | {r['after_unload_mib']} ({'yes' if r['returned_to_baseline'] else 'NO'}) |")
    L.append(f"\n- num_ctx {r['num_ctx']}: `ollama ps` model size {r['ps_size_bytes']} B, in VRAM {r['ps_size_vram_bytes']} B, context_length {r['ps_context_length']}; "
             f"load {r['load_s']} s, wall {r['wall_s']} s; extra passages {r['n_extra_chunks']}; sanity {json.dumps(r['sensible'], ensure_ascii=False)}; notes {r['notes'] or 'none'}.\n")
    with open(out, "a") as f:
        f.write("\n".join(L))
    print("appended to", out, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", metavar="CTX:TARGET", help="padded run, e.g. 8192:7000 (repeatable)")
    args = ap.parse_args()
    if args.run:
        return padded_main([tuple(int(x) for x in r.split(":")) for r in args.run])
    if (REPO / 'docs/measurements' / f'{dt.date.today().isoformat()}_ollama_contract.md').exists():
        raise SystemExit('Default mode rewrites today\'s measurements file; it already exists. Use --run for padded runs.')
    messages, source_text, meta = build_prompt()
    ps = httpx.get(f"{BASE}/api/ps", timeout=10).json().get("models", [])
    if ps:
        raise SystemExit(f"A model is already loaded: {[m['name'] for m in ps]}. Unload it first.")
    results = []
    for num_ctx in CTX_SIZES:
        baseline = settle_baseline()
        r = run_one(messages, source_text, num_ctx, baseline)
        r["unloaded"] = unload()
        time.sleep(2)
        r["after_unload_mib"] = settle_baseline()
        r["returned_to_baseline"] = abs(r["after_unload_mib"] - baseline) <= 200
        results.append(r)
        print(json.dumps(r, indent=1))
    full = max(r["prompt_eval_count"] or 0 for r in results)
    for r in results:
        pe = r["prompt_eval_count"] or 0
        r["prompt_truncated"] = pe < full or pe >= int(r["num_ctx"] * 0.98)
    write_report(results, meta)


def write_report(results, meta):
    today = dt.date.today().isoformat()
    out = REPO / "docs/measurements" / f"{today}_ollama_contract.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    full = max(r["prompt_eval_count"] or 0 for r in results)
    L = [f"# Ollama contract probe ({today})", "",
         f"Model `{MODEL}`, `think: false`, `temperature: 0`, `seed: 42`, `num_predict: {NUM_PREDICT}`, `keep_alive: 10m`, JSON Schema `format`. "
         "Tool: `tools/ollama_contract_probe.py`. GPU: RTX 3070, 8192 MiB. Memory read from host `nvidia-smi` (whole GPU, polled every 0.2 s in a background thread) around each call.", "",
         "Prompt: system prompt + 5 consecutive 30 s windows of the Day 4 transcript "
         f"(from {meta['first_window_start_s']} s; {meta['transcript_words']} words, the 5 densest consecutive windows in the first 10 min) "
         f"+ 2 placeholder ML textbook chunks ({meta['textbook_words'][0]} and {meta['textbook_words'][1]} words; placeholder text, not the chosen textbook).", "",
         "| num_ctx | baseline MiB | peak MiB | model share MiB (peak - baseline) | free at peak MiB | PROCESSOR (`ollama ps`) | prompt_eval_count | truncated? | out tokens | tok/s | JSON valid | after unload MiB (within 200 of baseline?) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['num_ctx']} | {r['baseline_mib']} | {r['peak_mib']} | {r['model_share_mib']} | {r['free_at_peak_mib']} | {r['processor']} | {r['prompt_eval_count']} | {'YES' if r['prompt_truncated'] else 'no'} | {r['eval_count']} | {r['tokens_per_sec']} | {r['json_valid']} | {r['after_unload_mib']} ({'yes' if r['returned_to_baseline'] else 'NO'}) |")
    L += ["", "## Details", ""]
    for r in results:
        L += [f"### num_ctx {r['num_ctx']}", "",
              f"- `ollama ps`: `{r['processor']}`; model size {r['ps_size_bytes']} B, of which in VRAM {r['ps_size_vram_bytes']} B; context_length {r['ps_context_length']}.",
              f"- done_reason `{r['done_reason']}`, thinking text present: {r['thinking_present']}, load {r['load_s']} s, wall {r['wall_s']} s, VRAM samples {r['vram_samples']}.",
              f"- Sanity of output: {json.dumps(r['sensible'], ensure_ascii=False)}; notes: {r['notes'] or 'none'}.", ""]
    L += ["## Reading the numbers", "",
          f"- Largest prompt_eval_count seen: {full}. Truncation is flagged when a run saw fewer prompt tokens than the largest run, or when the count is within 2% of num_ctx.",
          "- Baseline includes whatever the Windows desktop holds at that moment; the model's own share is peak minus that baseline.",
          "- The earlier figures in `ENV_AUDIT_REPORT.md` (7,566 MiB peak, 626 MiB headroom) were not re-run here and are not confirmed by this file.", ""]
    out.write_text("\n".join(L))
    print("wrote", out)


if __name__ == "__main__":
    main()
