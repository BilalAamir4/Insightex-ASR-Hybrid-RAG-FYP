"""C4 informational figures (ADR-0048 Amendment 10, decision 8; Bilal's request of 9 Nov 2026). Decide nothing.

1. Window 1/4/6 dependence: the window win count with windows 1, 4 and 6 left out (their context is a reserved
   window whose English gloss is in the frozen prompt's examples), and the best case for arm B in those windows.
2. Carry-over: model concepts that string-match (ADR-0048 section 4 normalisation) a gold concept of the previous
   window but no gold concept of the target window. Computed for arm B and, as a baseline, arm A (which never saw the
   previous window). Previous windows that are reserved (0, 3, 5) have no gold, so their targets are not countable.

Run from tools/label_concepts:  python ../../docs/evidence/m7/<lecture>/C4/scripts/c4_informational.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from matching import concept_keys  # noqa: E402

LECTURE = "sha256-de27cb67c2acbedebd0c2c7416932b8a"
C4 = Path(__file__).resolve().parents[1]
GOLD = Path("labels") / LECTURE / "gold_v2_1.json"
RESERVED_CONTEXT = (1, 4, 6)


def records(path: Path) -> dict[int, dict]:
    return {w["window"]["window_index"]: w for w in json.loads(path.read_text(encoding="utf-8"))["windows"]}


def main() -> int:
    comp = json.loads((C4 / "compare_C4_gold_v2_1.json").read_text(encoding="utf-8"))["comparison"]
    per = {w["window_index"]: w["winner"] for w in comp["per_window"]}
    rest = {i: w for i, w in per.items() if i not in RESERVED_CONTEXT}
    a, b = sum(w == "a" for w in rest.values()), sum(w == "b" for w in rest.values())
    out = {"window_wins_without_1_4_6": {"a": a, "b": b, "tied": len(rest) - a - b, "net_b": b - a},
           "outcomes_in_1_4_6": {i: per[i] for i in RESERVED_CONTEXT},
           "best_case_net_b_if_1_4_6_all_b": b + len(RESERVED_CONTEXT) - a}
    gold = records(GOLD)
    gold_keys = {i: set().union(*(concept_keys(c) for c in r["concepts"])) if r["concepts"] else set()
                 for i, r in gold.items()}
    carry = {}
    for arm in ("C4-window", "C4-previous"):
        recs = records(C4 / arm / "extraction.json")
        rows, countable = [], 0
        for t, rec in sorted(recs.items()):
            prev = t - 1
            if prev not in gold:  # reserved previous window: no gold to compare with
                continue
            countable += 1
            for c in rec["concepts"]:
                k = concept_keys(c)
                if k & gold_keys[prev] and not k & gold_keys.get(t, set()):
                    rows.append({"window": t, "label": c["label"]})
        carry[arm] = {"countable_windows": countable, "carry_over_concepts": len(rows), "items": rows}
    out["carry_over"] = carry
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (C4 / "c4_informational.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
