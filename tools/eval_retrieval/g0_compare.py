#!/usr/bin/env python3
"""Gate G0 equivalence check (ADR-0043): production encoder vs the legacy bake-off encoder, by ranking.

Standalone: imports nothing from backend/src. It imports the restored legacy bake-off script (`embed_bakeoff.py`, from
tag `import-baseline`, kept outside the repo) to reuse its SRT parser and window builder, and repeats its model lines
(SentenceTransformer, float16 on cuda, max_seq_length, batch 16, normalised, FAISS IndexFlatIP) for encoding.

Inputs: the lecture's production `windows.json`, the production search result (`score.py run --k 10 --device cuda`),
the gold questions. Check 1: the legacy window builder, fed one cue per production window, reproduces the production
windows (times and texts). Check 2: for every query the top-10 window order is identical and cosine scores match within
--tol. Uses the GPU: free it first (unload Ollama).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def load_legacy(path: Path):
    spec = importlib.util.spec_from_file_location("embed_bakeoff", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["embed_bakeoff"] = mod
    spec.loader.exec_module(mod)
    return mod


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--legacy", required=True, help="path to the restored embed_bakeoff.py")
    p.add_argument("--windows", required=True, help="production windows.json")
    p.add_argument("--production", required=True, help="JSON printed by `insightex search --k 10 --device cuda`")
    p.add_argument("--questions", required=True, help="JSON list of {id, question}")
    p.add_argument("--out", required=True)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    legacy = load_legacy(Path(args.legacy))
    prod_windows = json.loads(Path(args.windows).read_text(encoding="utf-8"))["windows"]
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))

    # Check 1: legacy window builder over one cue per production window
    with tempfile.TemporaryDirectory() as tmp:
        srt = Path(tmp) / "windows.srt"
        srt.write_text("\n".join(f"{i + 1}\n{srt_time(w['start'])} --> {srt_time(w['end'])}\n{w['text']}\n"
                                 for i, w in enumerate(prod_windows)), encoding="utf-8")
        cues = legacy.parse_srt(str(srt))
    legacy_windows = legacy.create_windows(cues, window_sec=30.0, stride_sec=30.0)
    windows_match = (len(legacy_windows) == len(prod_windows) and all(
        abs(a.start_sec - b["start"]) < 1e-6 and a.text == b["text"] for a, b in zip(legacy_windows, prod_windows, strict=True)))
    print(f"window check: legacy {len(legacy_windows)} vs production {len(prod_windows)} windows -> {'MATCH' if windows_match else 'DIFFER'}")

    # Check 2: legacy encoder on the same window texts, same queries
    import faiss
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-m3", model_kwargs={"torch_dtype": torch.float16}, device="cuda")
    model.max_seq_length = 1024
    win_vecs = model.encode([w["text"] for w in prod_windows], batch_size=16, normalize_embeddings=True, show_progress_bar=False)
    q_vecs = model.encode([q["question"] for q in questions], batch_size=16, normalize_embeddings=True, show_progress_bar=False)
    index = faiss.IndexFlatIP(win_vecs.shape[1])
    index.add(win_vecs.astype(np.float32))
    scores, ids = index.search(q_vecs.astype(np.float32), len(prod_windows))

    prod = {r["id"]: r["hits"] for r in json.loads(Path(args.production).read_text(encoding="utf-8"))["results"]}
    rows, worst = [], 0.0
    for qi, q in enumerate(questions):
        ph = prod[q["id"]][: args.top]
        n = len(ph)
        legacy_order = [int(i) for i in ids[qi][:n]]
        prod_order = [h["window_id"] for h in ph]
        diff = max(abs(float(scores[qi][r]) - ph[r]["score"]) for r in range(n))
        worst = max(worst, diff)
        rows.append({"id": q["id"], "order_identical": legacy_order == prod_order, "max_abs_score_diff": diff,
                     "legacy_top": legacy_order, "production_top": prod_order})
    bad = [r for r in rows if not r["order_identical"] or r["max_abs_score_diff"] > args.tol]
    result = {"windows_match": windows_match, "queries": len(rows), "tol": args.tol, "top": args.top,
              "worst_abs_score_diff": worst, "differing_queries": [r["id"] for r in bad], "pass": windows_match and not bad,
              "rows": rows}
    Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"{len(rows)} queries: worst |score diff| = {worst:.2e}; differing queries: {result['differing_queries'] or 'none'}")
    print("G0 equivalence:", "PASS" if result["pass"] else "FAIL")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
