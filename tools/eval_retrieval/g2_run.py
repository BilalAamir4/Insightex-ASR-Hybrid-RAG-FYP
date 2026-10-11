#!/usr/bin/env python3
"""Gate G2 (ADR-0043): dense only (A) against dense + sparse fused with Reciprocal Rank Fusion, k=60 (B).

Standalone. Inputs: the full dense ranking of every gold question from `insightex search --k <all windows>` (the
production index; this is A and also B's dense list), and the lecture's `windows.json`. The sparse side is computed here
with `sparse.SparseEncoder` (fp16 on the GPU, batch 16, max length 1024, like the document path): each window's and each
question's sparse weights, the lexical score of every window, and a sparse ranking of the windows with a score above 0
(ties by window id). B's ranking is RRF over the dense ranking and that sparse ranking. Writes B and a sparse-only run in
the `insightex search` JSON shape, so `score.py compare` and `score.py score` read them. Uses the GPU: free it first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse import SparseEncoder, rrf, sparse_score  # noqa: E402


def run_json(base: dict, name: str, rankings: dict[str, list[tuple[int, float]]], windows: list[dict], questions: list[dict], k: int) -> dict:
    out = {key: base[key] for key in ("lecture", "index_config_id", "index_fingerprint", "index")}
    out.update({"method": name, "k": k, "results": []})
    for q in questions:
        hits = [{"rank": r, "window_id": wid, "start": windows[wid]["start"], "end": windows[wid]["end"], "score": s}
                for r, (wid, s) in enumerate(rankings[q["id"]][:k], start=1)]
        out["results"].append({"id": q["id"], "question": q["question"], "hits": hits})
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dense", required=True, help="insightex search JSON with ALL windows ranked per question")
    p.add_argument("--windows", required=True)
    p.add_argument("--questions", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--rrf-k", type=int, default=60)
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()
    dense = json.loads(Path(args.dense).read_text(encoding="utf-8"))
    windows = json.loads(Path(args.windows).read_text(encoding="utf-8"))["windows"]
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in dense["results"]}
    assert all(len(by_id[q["id"]]["hits"]) == len(windows) for q in questions), "dense run must rank every window"

    enc = SparseEncoder(device="cuda", dtype="float16", batch_size=16, max_length=1024)
    _, w_sparse = enc.encode([w["text"] for w in windows])
    _, q_sparse = enc.encode([q["question"] for q in questions])

    fused, sparse_only, diag = {}, {}, []
    for q, qs in zip(questions, q_sparse, strict=True):
        scores = [sparse_score(qs, ws) for ws in w_sparse]
        sparse_rank = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: (-scores[i], i))
        dense_rank = [h["window_id"] for h in by_id[q["id"]]["hits"]]
        order = rrf([dense_rank, sparse_rank], k=args.rrf_k)
        rr = {}
        for ranking in (dense_rank, sparse_rank):
            for rank, wid in enumerate(ranking, start=1):
                rr[wid] = rr.get(wid, 0.0) + 1.0 / (args.rrf_k + rank)
        fused[q["id"]] = [(wid, rr[wid]) for wid in order]
        sparse_only[q["id"]] = [(i, scores[i]) for i in sparse_rank]
        diag.append({"id": q["id"], "sparse_tokens": len(qs), "windows_with_sparse_score": len(sparse_rank)})
    out = Path(args.out_dir)
    (out / "g2_B_rrf.json").write_text(json.dumps(run_json(dense, "dense+sparse RRF k=%d" % args.rrf_k, fused, windows, questions, args.top), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "g2_sparse_only.json").write_text(json.dumps(run_json(dense, "sparse only", sparse_only, windows, questions, args.top), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "g2_sparse_diag.json").write_text(json.dumps(diag, indent=1), encoding="utf-8")
    print("wrote g2_B_rrf.json, g2_sparse_only.json, g2_sparse_diag.json to", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
