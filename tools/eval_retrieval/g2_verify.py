#!/usr/bin/env python3
"""G2 pre-check (ADR-0043): our BGE-M3 sparse head against `BGEM3FlagModel`, on the lecture's windows and the gold questions.

Run it with a Python that has FlagEmbedding (a throwaway venv, never the project venv). Pass: for every text the sparse
weights match within --tol (same token ids, weights within tol) and the dense vectors have cosine >= --min-cos with the
reference's. Batch size 1 removes padding differences, so the check isolates the head and the pooling; a batch-16 run of
our encoder against batch 1 is reported to show the size of the fp16 batching noise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse import SparseEncoder


def reference(texts, *, use_fp16: bool, batch_size: int, device: str, model_dir: str):
    from FlagEmbedding import BGEM3FlagModel

    m = BGEM3FlagModel(model_dir, use_fp16=use_fp16, devices=device)
    out = m.encode(texts, batch_size=batch_size, max_length=1024, return_dense=True, return_sparse=True,
                   return_colbert_vecs=False)
    sp = [{int(k): float(v) for k, v in d.items()} for d in out["lexical_weights"]]
    del m
    return np.asarray(out["dense_vecs"], dtype=np.float32), sp


def compare(a_dense, a_sparse, b_dense, b_sparse):
    cos = (a_dense * b_dense).sum(axis=1) / (np.linalg.norm(a_dense, axis=1) * np.linalg.norm(b_dense, axis=1))
    same_ids = sum(set(x) == set(y) for x, y in zip(a_sparse, b_sparse, strict=True))
    worst = 0.0
    for x, y in zip(a_sparse, b_sparse, strict=True):
        for t in set(x) | set(y):
            worst = max(worst, abs(x.get(t, 0.0) - y.get(t, 0.0)))
    return {"texts": len(a_sparse), "same_token_set": same_ids, "max_abs_weight_diff": worst, "min_dense_cosine": float(cos.min())}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--windows", required=True)
    p.add_argument("--questions", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model-dir", required=True, help="local BGE-M3 directory the reference loads: it must contain "
                   "sparse_linear.pt AND colbert_linear.pt, else FlagEmbedding silently random-initialises BOTH heads")
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--min-cos", type=float, default=0.9999)
    args = p.parse_args()
    windows = [w["text"] for w in json.loads(Path(args.windows).read_text(encoding="utf-8"))["windows"]]
    questions = [q["question"] for q in json.loads(Path(args.questions).read_text(encoding="utf-8"))]
    texts = windows + questions
    results = {}
    for name, dtype, device in (("fp16_gpu", "float16", "cuda"), ("fp32_gpu", "float32", "cuda")):
        ref_dense, ref_sparse = reference(texts, use_fp16=dtype == "float16", batch_size=1, device=device,
                                         model_dir=args.model_dir)
        enc = SparseEncoder(device=device, dtype=dtype, batch_size=1)
        our_dense, our_sparse = enc.encode(texts)
        r = compare(our_dense, our_sparse, ref_dense, ref_sparse)
        r["pass"] = r["same_token_set"] == r["texts"] and r["max_abs_weight_diff"] <= args.tol and r["min_dense_cosine"] >= args.min_cos
        results[name + "_batch1"] = r
        if name == "fp16_gpu":
            d16, s16 = SparseEncoder(device=device, dtype=dtype, batch_size=16).encode(texts)
            results["ours_fp16_batch16_vs_batch1"] = compare(d16, s16, our_dense, our_sparse)
        del enc
        import torch

        torch.cuda.empty_cache()
        print(name, json.dumps(r))
    results["windows"], results["questions"] = len(windows), len(questions)
    results["pass"] = all(v["pass"] for k, v in results.items() if k.endswith("_gpu_batch1"))
    Path(args.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("ours batch16 vs batch1 (fp16 noise):", json.dumps(results["ours_fp16_batch16_vs_batch1"]))
    print("G2 pre-check:", "PASS" if results["pass"] else "FAIL")
    return 0 if results["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
