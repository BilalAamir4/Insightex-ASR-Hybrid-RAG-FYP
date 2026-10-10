#!/usr/bin/env python3
"""Test A scorer (ADR-0043). Standalone: no imports from backend/src.

Production code is reached only through the CLI (`insightex search ... --k N` prints ranked windows as JSON).

    score.py score   --search run.json [--gold gold_spans.json] [--subset all|g23|en|roman|...] [--table]
    score.py compare --a runA.json --b runB.json [--subset g23] [--table]
    score.py run     --lecture W --out run.json [--device cuda] [--k 10]   (calls `insightex search`, saves its JSON)

Rules (ADR-0043):
- Hit: a window covers >= 50% of any one gold span of the query (overlap seconds / span length).
- Before taking the top 3, drop any window that overlaps a higher-ranked kept window by more than 50% of its own length.
- Recall@3 is the primary metric; MRR (first hit rank in the de-duplicated list, 0 if none) is reported, never decides.
- Net count: wins (B hit, A miss) minus losses (A hit, B miss) >= 2 adopts B; anything less keeps A.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HIT_COVERAGE = 0.5
DEDUPE_OVERLAP = 0.5
TOP_N = 3

# Query subsets. g23 = the 24 queries ADR-0043 uses for gates G2 and G3 (A01-A23 + A28).
SUBSETS = {
    "all": lambda q: True,
    "g23": lambda q: q["id"] in {f"A{i:02d}" for i in range(1, 24)} | {"A28"},
    "english": lambda q: q["set"] in ("en", "hard"),  # the English-only set (A01-A23)
    "roman": lambda q: q["set"] == "roman",
}


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def dedupe(hits: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for h in hits:
        length = h["end"] - h["start"]
        if length > 0 and any(overlap(h["start"], h["end"], k["start"], k["end"]) > DEDUPE_OVERLAP * length for k in kept):
            continue
        kept.append(h)
    return kept


def is_hit(window: dict, spans: list[list[float]]) -> bool:
    return any(overlap(window["start"], window["end"], s0, s1) >= HIT_COVERAGE * (s1 - s0) for s0, s1 in spans)


def score_query(hits: list[dict], spans: list[list[float]]) -> dict:
    kept = dedupe(hits)
    first = next((r for r, h in enumerate(kept, start=1) if is_hit(h, spans)), None)
    return {"hit3": first is not None and first <= TOP_N, "rr": 0.0 if first is None else 1.0 / first,
            "first_rank": first, "top3": [(h["start"], h["end"], round(h["score"], 4)) for h in kept[:TOP_N]]}


def load_gold(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def score_run(run: dict, gold: list[dict], subset: str) -> dict[str, dict]:
    by_id = {r["id"]: r for r in run["results"]}
    return {q["id"]: score_query(by_id[q["id"]]["hits"], q["spans"]) for q in gold if SUBSETS[subset](q)}


def summary(scores: dict[str, dict]) -> dict:
    n = len(scores)
    return {"n": n, "recall_at_3": sum(s["hit3"] for s in scores.values()) / n if n else None,
            "mrr": sum(s["rr"] for s in scores.values()) / n if n else None}


def fmt(x) -> str:
    return "-" if x is None else f"{x:.4f}"


def cmd_score(args) -> int:
    gold = load_gold(Path(args.gold))
    run = json.loads(Path(args.search).read_text(encoding="utf-8"))
    out = {"search": args.search, "gold": args.gold, "subsets": {}}
    for name in ("all", "g23", "english", "roman"):
        scores = score_run(run, gold, name)
        out["subsets"][name] = summary(scores)
        print(f"{name:8} n={out['subsets'][name]['n']:2} Recall@3={fmt(out['subsets'][name]['recall_at_3'])} MRR={fmt(out['subsets'][name]['mrr'])}")
    if args.table:
        for qid, s in score_run(run, gold, args.subset).items():
            print(f"{qid:5} hit3={int(s['hit3'])} rank={s['first_rank']} top3={s['top3']}")
    if args.json_out:
        out["per_query"] = score_run(run, gold, "all")
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


def cmd_compare(args) -> int:
    gold = load_gold(Path(args.gold))
    ra = json.loads(Path(args.a).read_text(encoding="utf-8"))
    rb = json.loads(Path(args.b).read_text(encoding="utf-8"))
    sa, sb = score_run(ra, gold, args.subset), score_run(rb, gold, args.subset)
    wins = [q for q in sa if sb[q]["hit3"] and not sa[q]["hit3"]]
    losses = [q for q in sa if sa[q]["hit3"] and not sb[q]["hit3"]]
    net = len(wins) - len(losses)
    print(f"subset {args.subset} (n={len(sa)})")
    print(f"{'id':5} {'A hit':6} {'B hit':6}")
    for q in sa:
        print(f"{q:5} {int(sa[q]['hit3']):<6} {int(sb[q]['hit3']):<6}{'  win' if q in wins else '  LOSS' if q in losses else ''}")
    A, B = summary(sa), summary(sb)
    print(f"A: Recall@3={fmt(A['recall_at_3'])} MRR={fmt(A['mrr'])}   B: Recall@3={fmt(B['recall_at_3'])} MRR={fmt(B['mrr'])}")
    print(f"wins={len(wins)} losses={len(losses)} net={net} -> {'ADOPT B' if net >= 2 else 'KEEP A (tie or worse)'}")
    return 0


def cmd_run(args) -> int:
    cmd = [*args.cli.split(), "search", args.lecture, "--queries-file", args.queries, "--k", str(args.k)]
    if args.device:
        cmd += ["--device", args.device]
    if args.dtype:
        cmd += ["--dtype", args.dtype]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        return out.returncode
    Path(args.out).write_text(out.stdout, encoding="utf-8")
    return 0


def questions_file(gold: list[dict], path: Path) -> None:
    path.write_text(json.dumps([{"id": q["id"], "question": q["question"]} for q in gold], ensure_ascii=False), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--search", required=True)
    s.add_argument("--gold", default=str(HERE / "gold_spans.json"))
    s.add_argument("--subset", default="all", choices=list(SUBSETS))
    s.add_argument("--table", action="store_true")
    s.add_argument("--json-out")
    s.set_defaults(func=cmd_score)
    c = sub.add_parser("compare")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--gold", default=str(HERE / "gold_spans.json"))
    c.add_argument("--subset", default="g23", choices=list(SUBSETS))
    c.set_defaults(func=cmd_compare)
    r = sub.add_parser("run")
    r.add_argument("--lecture", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--queries", default=str(HERE / "gold_questions.json"), help="JSON list of {id, question} (see `questions`)")
    r.add_argument("--k", type=int, default=10)
    r.add_argument("--device", choices=["cpu", "cuda"])
    r.add_argument("--dtype", choices=["float32", "float16"])
    r.add_argument("--cli", default="bash scripts/run_in_env.sh python -m insightex.cli", help="how to start the insightex CLI")
    r.set_defaults(func=cmd_run)
    q = sub.add_parser("questions", help="write the {id, question} list of the gold file for `run`")
    q.add_argument("--gold", default=str(HERE / "gold_spans.json"))
    q.add_argument("--out", default=str(HERE / "gold_questions.json"))
    q.set_defaults(func=lambda a: (questions_file(load_gold(Path(a.gold)), Path(a.out)), 0)[1])
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
