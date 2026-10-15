"""Concept and relation matching between two label sets for one window (ADR-0048), and micro aggregation.

Concept match. A predicted concept matches a reference concept if, after `normalise` (NFKC, case-fold, punctuation,
whitespace and format characters removed), its label or any alias equals the reference label or any reference alias.
Matching is one-to-one: the pairs are a maximum bipartite matching over those string edges (Kuhn's algorithm, in list
order, so the result is deterministic). Then, for predicted concepts still unmatched, a frozen adjudication decides:
the entry for (window_index, normalised predicted label) names a reference label (match, used only if that reference
concept is still unmatched) or null (no match). Unmatched predicted concepts without an entry are pending: they count
as false positives and are listed so they can be put on the adjudication sheet.

Relation match. Both endpoints map to matched reference concepts and the type is equal; direction counts, except for
contrasts_with. Relations are compared as sets.

Per-window F1 when both sides are empty is 1.0 (nothing to find, nothing claimed); when only one side is empty it is 0.
Micro P/R/F1 sum true positives and set sizes over windows. Human-vs-human agreement uses the same code with one
labeller as the reference (F1 is symmetric under one-to-one matching; P and R swap).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extraction_schema import normalise, relation_key

ADJUDICATION_VERSION = 1
Adjudications = dict[tuple[int, str], "str | None"]


def concept_keys(concept: dict[str, Any]) -> set[str]:
    return {k for k in (normalise(n) for n in [concept["label"], *concept.get("aliases", [])]) if k}


def _max_matching(n_left: int, edges: list[list[int]], right_taken: dict[int, int]) -> dict[int, int]:
    """Kuhn's augmenting paths. edges[i] lists right nodes of left node i; right_taken maps right -> left and is
    extended in place. Returns left -> right."""

    def augment(i: int, seen: set[int]) -> bool:
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in right_taken or augment(right_taken[j], seen):
                right_taken[j] = i
                return True
        return False

    for i in range(n_left):
        augment(i, set())
    return {i: j for j, i in right_taken.items()}


@dataclass
class WindowScore:
    window_index: int
    concept_tp: int
    concept_pred: int
    concept_ref: int
    relation_tp: int
    relation_pred: int
    relation_ref: int
    important_pred: bool
    important_ref: bool
    pairs: list[tuple[str, str, str]] = field(default_factory=list)  # (pred label, ref label, "string"|"adjudicated")
    unmatched_pred: list[dict[str, Any]] = field(default_factory=list)
    pending_pred: list[dict[str, Any]] = field(default_factory=list)  # unmatched, no adjudication entry
    unmatched_ref: list[dict[str, Any]] = field(default_factory=list)

    @property
    def concept_f1(self) -> float:
        return f1(self.concept_tp, self.concept_pred, self.concept_ref)

    @property
    def relation_f1(self) -> float:
        return f1(self.relation_tp, self.relation_pred, self.relation_ref)


def f1(tp: int, n_pred: int, n_ref: int) -> float:
    if n_pred == 0 and n_ref == 0:
        return 1.0
    return 2 * tp / (n_pred + n_ref)


def ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def match_window(pred: dict[str, Any], ref: dict[str, Any], window_index: int,
                 adjudications: Adjudications | None = None) -> WindowScore:
    pc, rc = pred["concepts"], ref["concepts"]
    pkeys = [concept_keys(c) for c in pc]
    rkeys = [concept_keys(c) for c in rc]
    edges = [[j for j in range(len(rc)) if pkeys[i] & rkeys[j]] for i in range(len(pc))]
    taken: dict[int, int] = {}
    left = _max_matching(len(pc), edges, taken)
    how = {i: "string" for i in left}
    pending = []
    ref_index = {c["label"]: j for j, c in enumerate(rc)}
    for i, c in enumerate(pc):
        if i in left:
            continue
        key = (window_index, normalise(c["label"]))
        if adjudications is not None and key in adjudications:
            target = adjudications[key]
            j = ref_index.get(target) if target is not None else None
            if j is not None and j not in taken:
                taken[j] = i
                left[i] = j
                how[i] = "adjudicated"
        else:
            pending.append(c)
    mapping = {pc[i]["label"]: rc[j]["label"] for i, j in left.items()}
    ref_rel = {relation_key(r["head"], r["type"], r["tail"]) for r in ref["relations"]}
    pred_rel = {relation_key(r["head"], r["type"], r["tail"]) for r in pred["relations"]}
    mapped = {relation_key(mapping[h], t, mapping[tl]) for h, t, tl in pred_rel if h in mapping and tl in mapping}
    return WindowScore(
        window_index=window_index,
        concept_tp=len(left), concept_pred=len(pc), concept_ref=len(rc),
        relation_tp=len(mapped & ref_rel), relation_pred=len(pred_rel), relation_ref=len(ref_rel),
        important_pred=bool(pred["important"]), important_ref=bool(ref["important"]),
        pairs=[(pc[i]["label"], rc[j]["label"], how[i]) for i, j in sorted(left.items())],
        unmatched_pred=[c for i, c in enumerate(pc) if i not in left],
        pending_pred=pending,
        unmatched_ref=[c for j, c in enumerate(rc) if j not in taken],
    )


def micro(scores: list[WindowScore]) -> dict[str, Any]:
    ct = sum(s.concept_tp for s in scores)
    cp = sum(s.concept_pred for s in scores)
    cr = sum(s.concept_ref for s in scores)
    rt = sum(s.relation_tp for s in scores)
    rp = sum(s.relation_pred for s in scores)
    rr = sum(s.relation_ref for s in scores)
    it = sum(1 for s in scores if s.important_pred and s.important_ref)
    ip = sum(1 for s in scores if s.important_pred)
    ir = sum(1 for s in scores if s.important_ref)
    return {
        "windows": len(scores),
        "concept": {"tp": ct, "pred": cp, "ref": cr, "precision": ratio(ct, cp), "recall": ratio(ct, cr),
                    "f1": f1(ct, cp, cr)},
        "relation": {"tp": rt, "pred": rp, "ref": rr, "precision": ratio(rt, rp), "recall": ratio(rt, rr),
                     "f1": f1(rt, rp, rr)},
        "important": {"tp": it, "pred": ip, "ref": ir, "precision": ratio(it, ip), "recall": ratio(it, ir),
                      "agreement": ratio(sum(1 for s in scores if s.important_pred == s.important_ref), len(scores))},
    }


def load_adjudications(path: Path, lecture_id: str) -> Adjudications:
    """Adjudication file (ADR-0048): {"adjudication_version": 1, "lecture_id": ..., "entries": [{"window_index": int,
    "model_label": str, "gold_label": str | null, "decided_by": str, "decided_at": str}]}. Entries are append-only and
    never edited once a score has been reported with them."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("adjudication_version") != ADJUDICATION_VERSION or doc.get("lecture_id") != lecture_id:
        raise SystemExit(f"{path}: not a version {ADJUDICATION_VERSION} adjudication file for {lecture_id}")
    out: Adjudications = {}
    for e in doc["entries"]:
        key = (int(e["window_index"]), normalise(e["model_label"]))
        if key in out and out[key] != e["gold_label"]:
            raise SystemExit(f"{path}: conflicting entries for window {key[0]} label {e['model_label']!r}")
        out[key] = e["gold_label"]
    return out
