"""Score model extraction runs against the gold set and compare two arms (ADR-0048 sections 4 to 7, Amendments 1, 2).

An arm's run directory is written by `insightex extract-eval run` (backend/src/insightex/extract/harness.py) and holds
`extraction.json` (a schema v1 document with producer.kind = model and one record per window that came out valid) and
`run.json` (per window: valid or not after one retry, which attempt was used, relations dropped as dangling). This
module reads only those files, the gold file and the adjudications file; it never calls a model.

- Validity (section 7): an arm is valid only if every gold window has a valid record. An invalid arm is rejected
  whatever its score. Dangling relations were dropped before validation by the harness; their count is reported here.
- Concept matching (section 4): the string rule, one-to-one (matching.py); with adjudication, the frozen decisions in
  adjudications.json are applied to concepts the string rule left unmatched. Unmatched concepts without a decision
  are pending: they count as false positives, and `compare` refuses to decide while any are pending ("every decision
  is made before any arm is scored with adjudication").
- Metrics (section 6): micro concept P/R/F1 with adjudication (primary) and string rule only; relation P/R/F1;
  importance P/R over windows; per-window F1 (1.0 when both sides are empty).
- Comparison (section 7): per-window adjudicated concept F1 decides wins; net wins of 2 or fewer is a tie and keeps
  arm A; arm B is adopted only with net wins >= 3 and a micro F1 that is not lower.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from extraction_schema import check_document, normalise
from matching import Adjudications, WindowScore, match_window, micro

RUN_VERSION = 1  # run.json layout written by the extraction harness
NET_WINS_TO_ADOPT = 3  # ADR-0048 section 7: net wins of 2 or fewer is a tie
TIE_KEEPS = {  # ADR-0048 section 7 and Amendment 2: what arm A is, and why a tie keeps it
    "C1": "the model with the smaller measured VRAM peak at the worst-case prompt",
    "C2": "original-language input",
    "C3": "single-window calls",
    "C4": "window text only (no previous-window context)",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class ArmRun:
    name: str
    directory: Path
    doc: dict[str, Any]
    run: dict[str, Any]
    doc_sha256: str
    run_sha256: str


def parse_arm(spec: str) -> tuple[str, Path]:
    name, sep, directory = spec.partition("=")
    if not sep or not name.strip() or not directory.strip():
        raise SystemExit(f"--arm takes NAME=RUN_DIR, got {spec!r}")
    return name.strip(), Path(directory.strip())


def load_arm_run(name: str, directory: Path) -> ArmRun:
    doc_path, run_path = directory / "extraction.json", directory / "run.json"
    for p in (doc_path, run_path):
        if not p.is_file():
            raise SystemExit(f"arm {name}: no {p.name} in {directory}")
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("run_version") != RUN_VERSION:
        raise SystemExit(f"arm {name}: {run_path} is not a run_version {RUN_VERSION} file")
    return ArmRun(name, directory, doc, run, sha256_file(doc_path), sha256_file(run_path))


def load_gold(path: Path, lecture_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"no gold file at {path}; run `merge` first")
    gold = json.loads(path.read_text(encoding="utf-8"))
    errors = check_document(gold)
    if errors:
        raise SystemExit(f"{path} is invalid:\n  - " + "\n  - ".join(errors))
    if gold["lecture_id"] != lecture_id or gold["producer"]["kind"] != "human":
        raise SystemExit(f"{path} is not a human gold file for {lecture_id}")
    return gold


# -- validity ------------------------------------------------------------------------------------------------------


def arm_validity(arm: ArmRun, gold: dict[str, Any]) -> dict[str, Any]:
    """Section 7: every gold window must have a valid record (first response or one retry)."""
    schema_errors = check_document(arm.doc)
    problems: list[str] = []
    if not schema_errors:
        if arm.doc["lecture_id"] != gold["lecture_id"]:
            problems.append(f"lecture_id {arm.doc['lecture_id']!r} is not the gold's {gold['lecture_id']!r}")
        if arm.doc["producer"]["kind"] != "model":
            problems.append("producer.kind is not 'model'")
    status = {int(w["window_index"]): w for w in arm.run.get("windows", [])}
    records = {} if schema_errors else {r["window"]["window_index"]: r for r in arm.doc["windows"]}
    invalid, missing = [], []
    for g in gold["windows"]:
        i = g["window"]["window_index"]
        st = status.get(i)
        rec = records.get(i)
        if st is None:
            missing.append(i)
        elif not st.get("valid") or rec is None:
            invalid.append(i)
        elif (rec["window"]["start_s"], rec["window"]["end_s"]) != (g["window"]["start_s"], g["window"]["end_s"]):
            problems.append(f"window {i}: start/end differ from the gold")
            invalid.append(i)
    return {
        "valid": not (schema_errors or problems or invalid or missing),
        "schema_errors": schema_errors,
        "problems": problems,
        "invalid_windows": invalid,
        "missing_windows": missing,
        "retried_windows": sorted(i for i, st in status.items() if st.get("attempt_used") == 2),
        # valid only through the retry, with a record that has no concepts: reported apart from ordinary valid
        # windows (ADR-0049 Amendment 2); derived from the record, so older run.json files are covered too
        "valid_empty_after_retry_windows": sorted(
            g["window"]["window_index"] for g in gold["windows"]
            if (st := status.get(g["window"]["window_index"])) and st.get("valid") and st.get("attempt_used") == 2
            and (rec := records.get(g["window"]["window_index"])) is not None and not rec["concepts"]),
    }


def dropped_relations(arm: ArmRun, gold: dict[str, Any]) -> int:
    """Relations the harness dropped as dangling (endpoint not a concept of the window), summed over gold windows."""
    wanted = {g["window"]["window_index"] for g in gold["windows"]}
    return sum(int(w.get("dropped_relations", 0)) for w in arm.run.get("windows", []) if w["window_index"] in wanted)


# -- scoring -------------------------------------------------------------------------------------------------------


EMPTY = {"concepts": [], "relations": [], "important": False, "cue": None}


def window_scores(arm: ArmRun, gold: dict[str, Any], adjudications: Adjudications | None) -> list[WindowScore]:
    """One score per gold window, in gold order. A window the arm has no valid record for scores as empty (the arm is
    rejected by the validity rule anyway; the numbers are shown for information)."""
    records = {} if check_document(arm.doc) else {r["window"]["window_index"]: r for r in arm.doc["windows"]}
    return [match_window(records.get(g["window"]["window_index"], EMPTY), g, g["window"]["window_index"],
                         adjudications) for g in gold["windows"]]


def per_window_rows(scores: list[WindowScore]) -> list[dict[str, Any]]:
    return [{
        "window_index": s.window_index,
        "concept_tp": s.concept_tp, "concept_pred": s.concept_pred, "concept_ref": s.concept_ref,
        "concept_f1": s.concept_f1,
        "relation_tp": s.relation_tp, "relation_pred": s.relation_pred, "relation_ref": s.relation_ref,
        "important_pred": s.important_pred, "important_ref": s.important_ref,
        "pairs": [{"model": p, "gold": q, "by": how} for p, q, how in s.pairs],
        "unmatched_model": [c["label"] for c in s.unmatched_pred],
        "unmatched_gold": [c["label"] for c in s.unmatched_ref],
    } for s in scores]


def score_arm(arm: ArmRun, gold: dict[str, Any], adjudications: Adjudications) -> dict[str, Any]:
    string_only = window_scores(arm, gold, None)
    adjudicated = window_scores(arm, gold, adjudications)
    pending = [{"window_index": s.window_index, "model_label": c["label"]} for s in adjudicated for c in s.pending_pred]
    return {
        "name": arm.name,
        "run_dir": str(arm.directory),
        "extraction_sha256": arm.doc_sha256,
        "run_sha256": arm.run_sha256,
        "arm": arm.run.get("arm"),
        "prompt_sha256": arm.run.get("prompt_sha256"),
        "validity": arm_validity(arm, gold),
        "dropped_relations": dropped_relations(arm, gold),
        "adjudicated": {  # primary (section 6); decides comparisons
            "micro": micro(adjudicated),
            "pending": len(pending),
            "pending_concepts": pending,
            "per_window": per_window_rows(adjudicated),
        },
        "string_rule": {  # reported next to the primary; the only figure shown with the inter-annotator figure
            "micro": micro(string_only),
            "per_window": per_window_rows(string_only),
        },
    }


def micro_string_f1_on(score: dict[str, Any], window_indices: set[int]) -> float:
    """String-rule micro concept F1 restricted to some windows (e.g. the shared windows of the inter-annotator figure)."""
    rows = [r for r in score["string_rule"]["per_window"] if r["window_index"] in window_indices]
    tp, p, r = (sum(x[k] for x in rows) for k in ("concept_tp", "concept_pred", "concept_ref"))
    return 1.0 if p == 0 and r == 0 else 2 * tp / (p + r)


# -- comparison ----------------------------------------------------------------------------------------------------


def _f1(tp: int, n_pred: int, n_ref: int) -> Fraction:
    """Exact F1, so equal values compare equal (section 7 compares per-window and micro F1 for ties)."""
    return Fraction(1) if n_pred == 0 and n_ref == 0 else Fraction(2 * tp, n_pred + n_ref)


def compare(comparison: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Section 7 decision between arm A (kept on a tie) and arm B, on adjudicated per-window concept F1."""
    if comparison not in TIE_KEEPS:
        raise SystemExit(f"unknown comparison {comparison!r}; one of {', '.join(TIE_KEEPS)}")
    for s in (a, b):
        if s["adjudicated"]["pending"]:
            raise SystemExit(f"arm {s['name']}: {s['adjudicated']['pending']} unmatched concept(s) have no "
                             "adjudication yet; make the adjudication sheet and decide every entry before comparing")
    rows_a = {r["window_index"]: r for r in a["adjudicated"]["per_window"]}
    rows_b = {r["window_index"]: r for r in b["adjudicated"]["per_window"]}
    if list(rows_a) != list(rows_b):
        raise SystemExit("the two arms were scored on different windows")
    per_window, wins_a, wins_b = [], 0, 0
    for i, ra in rows_a.items():
        rb = rows_b[i]
        fa = _f1(ra["concept_tp"], ra["concept_pred"], ra["concept_ref"])
        fb = _f1(rb["concept_tp"], rb["concept_pred"], rb["concept_ref"])
        winner = "a" if fa > fb else "b" if fb > fa else "tie"
        wins_a += winner == "a"
        wins_b += winner == "b"
        per_window.append({"window_index": i, "f1_a": float(fa), "f1_b": float(fb), "winner": winner})
    ma, mb = a["adjudicated"]["micro"]["concept"], b["adjudicated"]["micro"]["concept"]
    micro_a, micro_b = _f1(ma["tp"], ma["pred"], ma["ref"]), _f1(mb["tp"], mb["pred"], mb["ref"])
    net = wins_b - wins_a
    va, vb = a["validity"]["valid"], b["validity"]["valid"]
    if not va and not vb:
        decision, reason = "no_decision", ("both arms fail the validity rule: fix the validation or retry handling "
                                           "(a new prompt freeze) and re-run both arms; never pick the arm that "
                                           "failed less")
    elif not vb:
        decision, reason = "keep_a", "arm B fails the validity rule and is rejected"
    elif not va:
        decision, reason = "adopt_b", "arm A fails the validity rule and is rejected"
    elif net < NET_WINS_TO_ADOPT:
        decision, reason = "keep_a", f"net wins for B = {net} (< {NET_WINS_TO_ADOPT}): a tie keeps arm A"
    elif micro_b < micro_a:
        decision, reason = "keep_a", f"net wins for B = {net} but its micro concept F1 is lower"
    else:
        decision, reason = "adopt_b", f"net wins for B = {net} (>= {NET_WINS_TO_ADOPT}) and micro F1 not lower"
    return {
        "comparison": comparison,
        "rule": "ADR-0048 section 7: per-window adjudicated concept F1; net wins >= 3 and micro F1 not lower adopts "
                "B; validity rule first",
        "arm_a": a["name"], "arm_b": b["name"],
        "tie_keeps_arm_a_because": TIE_KEEPS[comparison],
        "valid_a": va, "valid_b": vb,
        "valid_empty_after_retry_a": a["validity"]["valid_empty_after_retry_windows"],
        "valid_empty_after_retry_b": b["validity"]["valid_empty_after_retry_windows"],
        "wins_a": wins_a, "wins_b": wins_b, "ties": len(per_window) - wins_a - wins_b, "net_wins_b": net,
        "micro_concept_f1_a": float(micro_a), "micro_concept_f1_b": float(micro_b),
        "decision": decision, "reason": reason,
        "per_window": per_window,
    }


# -- adjudications file (append-only) --------------------------------------------------------------------------------


def adjudications_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "entries": 0, "sha256": None}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {"path": str(path), "exists": True, "entries": len(doc.get("entries", [])), "sha256": sha256_file(path)}


def adjudication_key(window_index: int, model_label: str) -> tuple[int, str]:
    return (int(window_index), normalise(model_label))
