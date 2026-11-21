"""ADR-0055 evidence (b): count self-pointing relations in the committed Day 4 run files (C1-C4), counts only.

Method, as written in ADR-0055 before counting:
  1. Read each arm's calls.jsonl.
  2. Keep extraction calls only (kind "extract"); translation calls have no relations.
  3. For each call whose content parses as JSON with a `windows` list, and each window record in it, look at each
     relation. It is a self-relation when head and tail are both strings, equal, and equal to the `label` of a concept
     in the same record. Equal head/tail values that are not a label of that record are counted separately (they
     would be dropped as dangling first).
  4. Per arm: totals, and per call (window_index, attempt, count). Per arm also the windows whose attempt was rejected
     *only* because of self-relations: the record has at least one self-relation, fails the unchanged validator as
     it is (after the harness's dangling drop), and passes it once its self-relations and dangling relations are
     removed.
  5. No labels, relation text or reply text is printed or written: only counts, window indices and attempt numbers.

C4-window is a byte copy of C1-gemma4-e4b (reused_from.json): it is checked to be identical and reported as such,
not counted twice. prompt_iteration/ is not part of C1-C4 and is not read. The held-out lecture is not read.
The validator is the standalone copy tools/label_concepts/extraction_schema.py (byte-identical to the production one).

    python3 docs/evidence/m7/session3/scripts/count_self_relations_day4.py
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
DAY4 = REPO / "docs" / "evidence" / "m7" / "sha256-de27cb67c2acbedebd0c2c7416932b8a"
OUT = REPO / "docs" / "evidence" / "m7" / "session3" / "self_relations_day4.json"
ARMS = ["C1/C1-gemma4-e4b", "C1/C1-qwen3.5", "C2/C2-original", "C2/C2-english", "C3/C3-single", "C3/C3-batch",
        "C4/C4-window", "C4/C4-previous"]
COPY_OF = {"C4/C4-window": "C1/C1-gemma4-e4b"}

spec = importlib.util.spec_from_file_location("extraction_schema",
                                              REPO / "tools" / "label_concepts" / "extraction_schema.py")
schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)


def labels_of(rec: dict) -> set:
    return {c.get("label") for c in rec.get("concepts", []) if isinstance(c, dict) and isinstance(c.get("label"), str)}


def is_self(r: object, labels: set) -> bool:
    return (isinstance(r, dict) and isinstance(r.get("head"), str) and r.get("head") == r.get("tail")
            and r["head"] in labels)


def is_equal_non_label(r: object, labels: set) -> bool:
    return (isinstance(r, dict) and isinstance(r.get("head"), str) and r.get("head") == r.get("tail")
            and r["head"] not in labels)


def dangling(r: object, labels: set) -> bool:  # the harness's drop_dangling rule
    return isinstance(r, dict) and not (r.get("head") in labels and r.get("tail") in labels)


def window_record(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "window_index"}


def count_arm(arm: str) -> dict:
    calls_out, rejected_only_self = [], []
    total_self = total_equal_non_label = 0
    for line in (DAY4 / arm / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        call = json.loads(line)
        if call.get("kind") != "extract" or not isinstance(call.get("content"), str):
            continue
        try:
            obj = json.loads(call["content"])
        except ValueError:
            continue
        items = obj.get("windows") if isinstance(obj, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("window_index"), int):
                continue
            rec = window_record(item)
            labels = labels_of(rec)
            rels = rec.get("relations") if isinstance(rec.get("relations"), list) else []
            n_self = sum(is_self(r, labels) for r in rels)
            n_eq = sum(is_equal_non_label(r, labels) for r in rels)
            total_self += n_self
            total_equal_non_label += n_eq
            calls_out.append({"window_index": item["window_index"], "attempt": call.get("attempt"),
                              "self_relations": n_self, "equal_head_tail_not_a_label": n_eq})
            if n_self:
                as_harness = copy.deepcopy(rec)
                as_harness["relations"] = [r for r in rels if not dangling(r, labels)]
                cleaned = copy.deepcopy(as_harness)
                cleaned["relations"] = [r for r in as_harness["relations"] if not is_self(r, labels)]
                if schema.check_labels(as_harness) and not schema.check_labels(cleaned):
                    rejected_only_self.append({"window_index": item["window_index"], "attempt": call.get("attempt")})
    return {"self_relations": total_self, "equal_head_tail_not_a_label": total_equal_non_label,
            "calls_with_self_relations": [c for c in calls_out if c["self_relations"]],
            "records_read": len(calls_out), "rejected_only_because_of_self_relations": rejected_only_self}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    result = {"method": "ADR-0055 Evidence (b); see this script's docstring", "lecture_id": DAY4.name, "arms": {}}
    for arm in ARMS:
        if arm in COPY_OF:
            src = COPY_OF[arm]
            identical = sha(DAY4 / arm / "calls.jsonl") == sha(DAY4 / src / "calls.jsonl")
            result["arms"][arm] = {"copy_of": src, "calls_jsonl_identical": identical,
                                   "note": "not counted twice" if identical else "NOT IDENTICAL: counted"}
            if identical:
                continue
        result["arms"][arm] = {**result["arms"].get(arm, {}), **count_arm(arm)}
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for arm, r in result["arms"].items():
        if "self_relations" in r:
            only = [(w["window_index"], w["attempt"]) for w in r["rejected_only_because_of_self_relations"]]
            print(f"{arm}: {r['records_read']} records, {r['self_relations']} self-relations, "
                  f"{r['equal_head_tail_not_a_label']} equal non-label; rejected only for self-relations: {only}")
        else:
            print(f"{arm}: copy of {r['copy_of']}, identical {r['calls_jsonl_identical']}")
    print(f"written: {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
