#!/usr/bin/env python3
"""Gate G1 helpers (ADR-0043): CPU fp32 queries through the API against the gate runs' GPU fp16 queries. Standalone.

    g1.py api     --base http://127.0.0.1:8000 --lecture W --questions q.json --out run.json [--pid P] [--k 10]
        One POST per question to /api/lectures/{W}/search (raw ranking: dedupe=false), one warm-up question first, then
        every question timed. Writes the `insightex search`-shaped run JSON plus latency (median, p95, max, ms) and, with
        --pid, the API process's peak resident memory (VmHWM) and current resident memory (VmRSS) read after the run.
    g1.py vectors --a A.npy --b B.npy --run-a runA.json --run-b runB.json
        Per-question cosine(A, B) (minimum reported) and agreement of the two runs' top-10 order.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.request
from pathlib import Path


def post(url: str, body: dict) -> tuple[dict, float]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    return data, (time.perf_counter() - t0) * 1000


def proc_kb(pid: int, field: str) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(field + ":"):
                return int(line.split()[1])
    except OSError:
        return None
    return None


def cmd_api(args) -> int:
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    url = f"{args.base}/api/lectures/{args.lecture}/search"
    rss_before = proc_kb(args.pid, "VmRSS") if args.pid else None
    _, first_ms = post(url, {"question": "warm-up question", "k": args.k, "dedupe": False})  # loads the model
    rss_loaded = proc_kb(args.pid, "VmRSS") if args.pid else None
    _, warm_ms = post(url, {"question": "second warm-up question", "k": args.k, "dedupe": False})
    results, times = [], []
    for q in questions:
        data, ms = post(url, {"question": q["question"], "k": args.k, "dedupe": False})
        times.append(ms)
        results.append({"id": q["id"], "question": q["question"], "hits": data["hits"]})
    times_sorted = sorted(times)
    p95 = times_sorted[math.ceil(0.95 * len(times_sorted)) - 1]  # nearest rank
    out = {"lecture": args.lecture, "index_config_id": data["index_config_id"], "method": "API CPU fp32, one question per request",
           "k": args.k, "results": results,
           "latency_ms": {"first_request_incl_model_load": round(first_ms, 1), "second_request": round(warm_ms, 1),
                          "n": len(times), "median": round(statistics.median(times), 1), "p95": round(p95, 1),
                          "max": round(max(times), 1), "min": round(min(times), 1)},
           "memory_kib": {"pid": args.pid, "VmRSS_before_first_request": rss_before, "VmRSS_after_model_load": rss_loaded,
                          "VmRSS_end": proc_kb(args.pid, "VmRSS") if args.pid else None,
                          "VmHWM_peak": proc_kb(args.pid, "VmHWM") if args.pid else None}}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("latency_ms", "memory_kib")}, indent=1))
    return 0


def cmd_vectors(args) -> int:
    import numpy as np

    a, b = np.load(args.a), np.load(args.b)
    cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    ra = {r["id"]: [h["window_id"] for h in r["hits"]] for r in json.loads(Path(args.run_a).read_text(encoding="utf-8"))["results"]}
    rb = {r["id"]: [h["window_id"] for h in r["hits"]] for r in json.loads(Path(args.run_b).read_text(encoding="utf-8"))["results"]}
    same_order = [q for q in ra if ra[q][:10] == rb[q][:10]]
    print(json.dumps({"queries": len(cos), "min_cosine": float(cos.min()), "median_cosine": float(np.median(cos)),
                      "argmin_index": int(cos.argmin()), "queries_below_0.999": int((cos < 0.999).sum()),
                      "top10_order_identical": len(same_order), "top10_order_differs": [q for q in ra if q not in same_order]}, indent=1))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("api")
    a.add_argument("--base", default="http://127.0.0.1:8000")
    a.add_argument("--lecture", required=True)
    a.add_argument("--questions", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--pid", type=int)
    a.add_argument("--k", type=int, default=10)
    a.set_defaults(func=cmd_api)
    v = sub.add_parser("vectors")
    for name in ("--a", "--b", "--run-a", "--run-b"):
        v.add_argument(name, required=True)
    v.set_defaults(func=cmd_vectors)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
