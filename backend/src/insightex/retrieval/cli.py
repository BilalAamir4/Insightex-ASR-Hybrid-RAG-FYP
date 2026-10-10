"""`insightex search`: rank one lecture's windows for one or more questions (ADR-0043, ADR-0044).

    insightex search <lecture_id> --query "..."            one question
    insightex search <lecture_id> --queries-file q.json    a JSON list of {"id": ..., "question": ...}

Prints one JSON document: the index's metadata, how the questions were encoded, and the best `--k` windows per
question (raw, in score order; `--dedupe` applies the overlap rule of `retrieval.dedupe_overlap`). This is the
only way the evaluation scorer in tools/eval_retrieval reaches production code. `--device cuda` takes the
exclusive GPU lease, which unloads the Ollama model first (ADR-0033); the default device is the configured
query device (CPU).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path

from insightex.core.config import ConfigError, load_settings
from insightex.index.store import load_index
from insightex.jobs.workspace import Workspaces
from insightex.retrieval import search as s


def _questions(args: argparse.Namespace) -> list[dict]:
    if args.query is not None:
        return [{"id": "q1", "question": args.query}]
    data = json.loads(Path(args.queries_file).read_text(encoding="utf-8"))
    return [{"id": str(q["id"]), "question": q["question"]} for q in data]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="insightex search")
    parser.add_argument("lecture", help="workspace id of the lecture")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query")
    group.add_argument("--queries-file")
    parser.add_argument("--k", type=int, help="windows per question (default: retrieval.candidates)")
    parser.add_argument("--dedupe", action="store_true", help="drop windows overlapping a higher-ranked one")
    parser.add_argument("--device", choices=["cpu", "cuda"], help="encode the questions here (default: retrieval.query_device)")
    parser.add_argument("--dtype", choices=["float32", "float16"], help="query model precision (default: retrieval.query_dtype)")
    parser.add_argument("--save-vectors", help="write the question vectors to this .npy file")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        questions = _questions(args)
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    directory = Workspaces(settings.jobs.workspaces_dir).stage_output_dir(args.lecture, "index")
    if directory is None:
        print(f"error: lecture {args.lecture!r} has no search index (ingest it first)", file=sys.stderr)
        return 1
    index = load_index(directory)
    try:
        s.check_compatible(settings, index)
    except s.IndexModelMismatch as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    encoder = s.QueryEncoder(settings, device=args.device, dtype=args.dtype)
    lease = nullcontext()
    if encoder.device == "cuda":
        from insightex.jobs.gpu_lease import FileGpuLease

        lease = FileGpuLease(settings).exclusive("search-cli", timeout_s=settings.gpu.qa_lease_timeout_s)
    with lease:
        t0 = time.monotonic()
        _ = encoder.model
        load_s = time.monotonic() - t0
        t0 = time.monotonic()
        vectors = encoder.encode([q["question"] for q in questions])
        encode_s = time.monotonic() - t0
    if args.save_vectors:
        import numpy as np

        np.save(args.save_vectors, vectors, allow_pickle=False)
    k = args.k or settings.retrieval.candidates
    ranked = s.search(index, vectors, k)
    results = []
    for q, hits in zip(questions, ranked, strict=True):
        if args.dedupe:
            hits = s.dedupe(hits, settings.retrieval.dedupe_overlap)
        results.append({"id": q["id"], "question": q["question"],
                        "hits": [{"rank": h.rank, "window_id": h.window_id, "start": h.start, "end": h.end,
                                  "score": h.score} for h in hits]})
    json.dump({"lecture": args.lecture, "index": index.meta,
               "encode": {"device": encoder.device, "dtype": encoder.dtype, "load_s": round(load_s, 3),
                          "encode_s": round(encode_s, 3), "questions": len(questions)},
               "dedupe": args.dedupe, "k": k, "results": results}, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
