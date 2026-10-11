#!/usr/bin/env python3
"""Gate G5 (ADR-0046): original-only search (A) against original + English rewrite fused with RRF k=60 (B). Standalone.

For every gold question: one rewrite call to Ollama with the pre-registered settings (prompt file, think false, temperature
0, num_ctx 8192, num_predict 64, keep_alive, the ADR's JSON schema; NO client timeout, so the true latency is measured),
one search of the original question and one search of the rewrite through the production API (CPU fp32, all windows ranked,
no de-duplication), then fusion here. The model is loaded and warmed with a question that is not in the gold set before
the timed calls. Rewrites that are unusable (ADR-0046) fall back to the original ranking, as production would.

Writes into --out-dir: g5_rewrites.json (every rewrite with its raw response fields and timing), g5_rewrites.md (the human
review table), g5_A_original.json and g5_B_fused.json (in the `insightex search` shape, for score.py), g5_summary.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse import rrf  # the RRF used in G2

SCHEMA = {"type": "object", "properties": {"english_question": {"type": "string", "minLength": 1, "maxLength": 300}},
          "required": ["english_question"], "additionalProperties": False}
TIMEOUT_S = 2.0  # the production timeout of ADR-0046; only counted here, never enforced
WARM_UP = "How many layers does a neural network usually have?"  # not a gold question


def post(url: str, body: dict, timeout: float = 600) -> tuple[dict, float]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data, time.perf_counter() - t0


def rewrite_call(ollama: str, model: str, system: str, question: str, num_ctx: int, num_predict: int, seed: int, keep_alive: str):
    body = {"model": model, "stream": False, "think": False, "format": SCHEMA, "keep_alive": keep_alive,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
            "options": {"num_ctx": num_ctx, "temperature": 0, "seed": seed, "num_predict": num_predict}}
    try:
        data, seconds = post(f"{ollama}/api/chat", body)
    except Exception as exc:  # noqa: BLE001 - recorded as a failed call
        return {"error": f"{type(exc).__name__}: {exc}", "usable": False, "problems": ["error"], "seconds": None, "rewrite": None}
    msg = data.get("message", {})
    content, thinking = msg.get("content", ""), msg.get("thinking") or ""
    problems, rewrite = [], None
    if data.get("done_reason") != "stop":
        problems.append(f"done_reason={data.get('done_reason')}")
    if "<think>" in content + thinking or "</think>" in content + thinking or thinking:
        problems.append("think text in the response")
    try:
        obj = json.loads(content)
        rewrite = obj["english_question"]
        if set(obj) != {"english_question"} or not isinstance(rewrite, str):
            problems.append("does not match the schema")
        elif not rewrite.strip():
            problems.append("empty rewrite")
        elif "\n" in rewrite:
            problems.append("newline in the rewrite")
        elif len(rewrite) > 300:
            problems.append("longer than 300 characters")
    except (ValueError, KeyError, TypeError):
        problems.append("not valid JSON for the schema")
    return {"error": None, "usable": not problems, "problems": problems, "seconds": seconds, "rewrite": rewrite, "raw_content": content,
            "done_reason": data.get("done_reason"), "eval_count": data.get("eval_count"), "prompt_eval_count": data.get("prompt_eval_count"),
            "total_duration_s": data.get("total_duration", 0) / 1e9, "load_duration_s": data.get("load_duration", 0) / 1e9}


def search_all(api: str, lecture: str, question: str, n_windows: int):
    data, seconds = post(f"{api}/api/lectures/{lecture}/search", {"question": question, "k": n_windows, "dedupe": False}, timeout=120)
    return data, seconds


def pctl(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[math.ceil(q * len(s)) - 1]  # nearest rank


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lecture", required=True)
    p.add_argument("--questions", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="qwen3.5:latest")
    p.add_argument("--num-ctx", type=int, default=8192)
    p.add_argument("--num-predict", type=int, default=64)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--keep-alive", default="10m")
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    system = Path(args.prompt).read_text(encoding="utf-8").rstrip("\n")
    prompt_sha = hashlib.sha256(Path(args.prompt).read_bytes()).hexdigest()
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))

    warm = rewrite_call(args.ollama, args.model, system, WARM_UP, args.num_ctx, args.num_predict, args.seed, args.keep_alive)
    print("warm-up:", {k: warm[k] for k in ("usable", "seconds", "rewrite", "load_duration_s") if k in warm})
    base, _ = search_all(args.api, args.lecture, "warm-up", 100)
    n_windows = len(base["hits"])

    rows, a_results, b_results = [], [], []
    for q in questions:
        rw = rewrite_call(args.ollama, args.model, system, q["question"], args.num_ctx, args.num_predict, args.seed, args.keep_alive)
        orig, _ = search_all(args.api, args.lecture, q["question"], n_windows)
        dense_orig = [h["window_id"] for h in orig["hits"]]
        windows = {h["window_id"]: h for h in orig["hits"]}
        second_s, fused_order, fell_back = None, dense_orig, True
        if rw["usable"]:
            rew, second_s = search_all(args.api, args.lecture, rw["rewrite"], n_windows)
            fused_order, fell_back = rrf([dense_orig, [h["window_id"] for h in rew["hits"]]], k=60), False
        score = {wid: 0.0 for wid in fused_order}
        if not fell_back:
            for ranking in (dense_orig, [h["window_id"] for h in rew["hits"]]):
                for r, wid in enumerate(ranking, start=1):
                    score[wid] += 1.0 / (60 + r)
        else:
            score = {wid: windows[wid]["score"] for wid in fused_order}
        a_results.append({"id": q["id"], "question": q["question"], "hits": orig["hits"][: args.top]})
        b_results.append({"id": q["id"], "question": q["question"], "hits": [
            {"rank": r, "window_id": wid, "start": windows[wid]["start"], "end": windows[wid]["end"], "score": score[wid]}
            for r, wid in enumerate(fused_order[: args.top], start=1)]})
        added = (rw["seconds"] or 0.0) + (second_s or 0.0)
        rows.append({"id": q["id"], "original": q["question"], "rewrite": rw["rewrite"], "usable": rw["usable"], "problems": rw["problems"],
                     "rewrite_s": rw["seconds"], "second_search_s": second_s, "added_s": added, "over_timeout": (rw["seconds"] is None) or rw["seconds"] > TIMEOUT_S,
                     "eval_count": rw.get("eval_count"), "done_reason": rw.get("done_reason"), "error": rw.get("error"), "raw_content": rw.get("raw_content")})
        print(q["id"], f"{rw['seconds'] and round(rw['seconds'], 2)}s", rw["usable"], "|", rw["rewrite"])

    secs = [r["rewrite_s"] for r in rows if r["rewrite_s"] is not None]
    added = [r["added_s"] for r in rows]
    would_fail = [r["id"] for r in rows if r["over_timeout"] or not r["usable"]]
    summary = {"prompt_sha256": prompt_sha, "model": args.model, "num_ctx": args.num_ctx, "num_predict": args.num_predict, "seed": args.seed,
               "questions": len(rows), "index_config_id": base["index_config_id"], "windows": n_windows,
               "rewrite_s": {"median": statistics.median(secs), "p95": pctl(secs, 0.95), "max": max(secs), "min": min(secs)},
               "added_s": {"median": statistics.median(added), "p95": pctl(added, 0.95), "max": max(added)},
               "unusable": [r["id"] for r in rows if not r["usable"]], "over_2s": [r["id"] for r in rows if r["over_timeout"] and r["usable"]],
               "would_hit_timeout_or_fail": would_fail, "count_would_hit_timeout_or_fail": len(would_fail)}
    (out / "g5_rewrites.json").write_text(json.dumps({"summary": summary, "rewrites": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "g5_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    md = ["# G5 rewrites (for human review)\n", f"Prompt sha256 `{prompt_sha}`; model `{args.model}`; every question rewritten once, no timeout.\n",
          "| id | original | rewrite | rewrite s | usable |", "|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['original']} | {r['rewrite']} | {r['rewrite_s'] and round(r['rewrite_s'], 2)} | {'yes' if r['usable'] else 'NO: ' + '; '.join(r['problems'])} |")
    (out / "g5_rewrites.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    common = {"lecture": args.lecture, "index_config_id": base["index_config_id"]}
    (out / "g5_A_original.json").write_text(json.dumps({**common, "method": "original only", "results": a_results}, ensure_ascii=False), encoding="utf-8")
    (out / "g5_B_fused.json").write_text(json.dumps({**common, "method": "original + rewrite, RRF k=60 (fallback: original)", "results": b_results}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
