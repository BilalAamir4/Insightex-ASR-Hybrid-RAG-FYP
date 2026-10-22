"""Gold relabelling pass (ADR-0048 Amendment 5): a reviewed copy of a frozen gold file, one decision per concept.

The pass starts from the frozen gold (`gold.json`, never changed) and keeps the reviewer's decisions in a state file
(`relabel_v2.json`). For each concept of each gold window the reviewer decides:
  keep    the concept stays; it may be renamed to one canonical name (a rename needs a reason);
  remove  the concept goes (needs a reason), and every relation that has it as head or tail goes with it.
A rename renames the concept's relation endpoints too, and drops an alias that becomes the same name as the new label
(after normalisation). Amendment 6 also lets the reviewer add a concept gold v1 never labelled (label, aliases and a
reason; no relations). Nothing else can change: the v1 aliases, the importance flag and the cue stay as they were.
Every change is appended to the state file's `log` with its time and reason. When every window is marked reviewed,
`merge` writes the new gold (`gold_v2.json`) from the frozen gold and the decisions alone.

State file: {"relabel_version": 1, "lecture_id", "pass", "rule", "base": {"file", "sha256"}, "created_at",
"windows": [{"window_index", "reviewed", "concepts": [{"v1_label", "decision": null|"keep"|"remove", "label",
"reason"}], "added": [{"id", "label", "aliases", "reason"}]}], "log": [{"at", "window_index", "v1_label" (null for the
window's reviewed flag and for additions), "field", "before", "after", "reason"} (additions also carry "added_id")]}.
A window without "added" (a state written before Amendment 6) has no additions.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from extraction_schema import NAME_MAX, check_document, check_window_record, normalise

RELABEL_VERSION = 1
PASSES = {"v2": {"base": "gold.json", "out": "gold_v2.json", "state": "relabel_v2.json"}}
DECISIONS = ("keep", "remove")
RULE = ("ADR-0048 Amendments 5 and 6: relabelling pass of the frozen Day 4 gold v1. Per concept: keep (optionally "
        "renamed to one canonical name, with a reason) or remove (with a reason; its relations go with it). A concept "
        "the window explains or uses substantively may be added (with a reason, no relations). The v1 aliases and "
        "importance are unchanged.")
ID_MAX = 64  # characters; the page's id for an added concept
# words left out when looking for labels that may name the same concept ("problem with X" / "problem of X")
VARIANT_STOPWORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"})


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths(lecture_dir: Path, pass_name: str) -> dict[str, Path]:
    if pass_name not in PASSES:
        raise SystemExit(f"unknown relabelling pass {pass_name!r} ({', '.join(PASSES)})")
    return {k: lecture_dir / v for k, v in PASSES[pass_name].items()}


def write_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# -- start ---------------------------------------------------------------------------------------------------------


def new_state(base: dict[str, Any], base_file: str, base_sha256: str, pass_name: str) -> dict[str, Any]:
    windows = []
    for rec in base["windows"]:
        windows.append({"window_index": rec["window"]["window_index"], "reviewed": False,
                        "concepts": [{"v1_label": c["label"], "decision": None, "label": c["label"], "reason": ""}
                                     for c in rec["concepts"]], "added": []})
    return {"relabel_version": RELABEL_VERSION, "lecture_id": base["lecture_id"], "pass": pass_name, "rule": RULE,
            "base": {"file": base_file, "sha256": base_sha256}, "created_at": now_utc(), "windows": windows,
            "log": []}


def load(state_path: Path, base_path: Path, lecture_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The state file and the frozen base gold, after checking that the base is the file the pass started from."""
    if not state_path.is_file():
        raise SystemExit(f"no {state_path.name}; run relabel-start first")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("relabel_version") != RELABEL_VERSION or state.get("lecture_id") != lecture_id:
        raise SystemExit(f"{state_path} is not a version {RELABEL_VERSION} relabelling state for {lecture_id}")
    if not base_path.is_file() or sha256_file(base_path) != state["base"]["sha256"]:
        raise SystemExit(f"{base_path.name} is missing or changed since the pass started (expected sha256 "
                         f"{state['base']['sha256']}); the frozen gold must never change")
    return state, json.loads(base_path.read_text(encoding="utf-8"))


# -- deriving the new record ----------------------------------------------------------------------------------------


def apply(base_rec: dict[str, Any], concepts: list[dict[str, Any]],
          added: list[dict[str, Any]] = ()) -> dict[str, Any]:
    """The window's new record: removed concepts and their relations dropped, kept ones renamed (relation endpoints
    follow), aliases equal to a new label dropped, added concepts after the v1 ones. An undecided concept is shown as
    kept."""
    by_v1 = {c["v1_label"]: c for c in concepts}
    removed = {c["v1_label"] for c in concepts if c["decision"] == "remove"}
    new_label = {c["v1_label"]: (c["label"].strip() or c["v1_label"]) for c in concepts if c["v1_label"] not in removed}
    out_concepts = []
    for c in base_rec["concepts"]:
        if c["label"] in removed:
            continue
        label = new_label[c["label"]] if c["label"] in by_v1 else c["label"]
        out_concepts.append({"label": label, "aliases": [a for a in c["aliases"] if normalise(a) != normalise(label)]})
    out_concepts.extend({"label": a["label"], "aliases": list(a["aliases"])} for a in added)
    relations = [{"head": new_label[r["head"]], "type": r["type"], "tail": new_label[r["tail"]]}
                 for r in base_rec["relations"] if r["head"] not in removed and r["tail"] not in removed]
    return {**base_rec, "concepts": out_concepts, "relations": relations}


# -- one window's decisions -----------------------------------------------------------------------------------------


def _needs_reason(c: dict[str, Any]) -> bool:
    return c["decision"] == "remove" or (c["decision"] == "keep" and c["label"] != c["v1_label"])


def check_added(items: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Errors in the window's additions [{"id", "label", "aliases", "reason"}], and the cleaned list (stripped strings,
    blank aliases dropped). The id is chosen by the page and only identifies the addition in the log."""
    if not isinstance(items, list):
        return ["added must be a list"], []
    errors: list[str] = []
    clean, ids = [], set()
    for n, a in enumerate(items):
        if not isinstance(a, dict) or set(a) != {"id", "label", "aliases", "reason"}:
            errors.append(f"added concept {n}: needs exactly id, label, aliases and reason")
            continue
        if not (isinstance(a["id"], str) and a["id"].strip() and len(a["id"]) <= ID_MAX) or a["id"] in ids:
            errors.append(f"added concept {n}: needs its own id")
            continue
        ids.add(a["id"])
        if not (isinstance(a["label"], str) and isinstance(a["reason"], str) and isinstance(a["aliases"], list)
                and all(isinstance(x, str) for x in a["aliases"])):
            errors.append(f"added concept {n}: label and reason must be text, aliases a list of text")
            continue
        d = {"id": a["id"], "label": " ".join(a["label"].split()),
             "aliases": [" ".join(x.split()) for x in a["aliases"] if x.strip()], "reason": " ".join(a["reason"].split())}
        name = repr(d["label"]) if d["label"] else f"added concept {n}"
        if not d["label"]:
            errors.append(f"{name}: an added concept needs a label")
        if not d["reason"]:
            errors.append(f"{name}: an addition needs a reason")
        if len(d["reason"]) > 1000:
            errors.append(f"{name}: reason too long")
        clean.append(d)
    return errors, clean


def check_payload(win: dict[str, Any], base_rec: dict[str, Any],
                  body: Any) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Errors in a PUT body {"reviewed": bool, "concepts": [{"v1_label", "decision", "label", "reason"}], "added":
    [...] (optional; left out = unchanged)}, the cleaned concept decisions (stripped strings; a removed concept keeps
    its v1 label) and the cleaned additions."""
    if not isinstance(body, dict) or not isinstance(body.get("reviewed"), bool) or not isinstance(
            body.get("concepts"), list):
        return ["body must be {\"reviewed\": true|false, \"concepts\": [...]}"], [], []
    expected = [c["v1_label"] for c in win["concepts"]]
    errors: list[str] = []
    clean = []
    for n, c in enumerate(body["concepts"]):
        if not isinstance(c, dict) or set(c) != {"v1_label", "decision", "label", "reason"}:
            errors.append(f"concept {n}: needs exactly v1_label, decision, label and reason")
            continue
        if c["decision"] not in (None, *DECISIONS):
            errors.append(f"{c['v1_label']!r}: decision must be keep, remove or not decided")
            continue
        if not all(isinstance(c[k], str) for k in ("v1_label", "label", "reason")):
            errors.append(f"concept {n}: v1_label, label and reason must be text")
            continue
        label = " ".join(c["label"].split())
        d = {"v1_label": c["v1_label"], "decision": c["decision"],
             "label": label if c["decision"] == "keep" else c["v1_label"], "reason": " ".join(c["reason"].split())}
        if c["decision"] == "keep" and not label:
            errors.append(f"{c['v1_label']!r}: a kept concept needs a label")
        if len(d["label"]) > NAME_MAX or len(d["reason"]) > 1000:
            errors.append(f"{c['v1_label']!r}: label or reason too long")
        if _needs_reason(d) and not d["reason"]:
            errors.append(f"{c['v1_label']!r}: a {'removal' if d['decision'] == 'remove' else 'rename'} needs a reason")
        clean.append(d)
    if [c.get("v1_label") for c in body["concepts"] if isinstance(c, dict)] != expected:
        errors.append(f"the concepts must be this window's gold v1 concepts, in order: {expected}")
    if body["reviewed"] and any(c["decision"] is None for c in clean):
        errors.append("every concept needs keep or remove before the window is marked reviewed")
    add_errors, added = check_added(body.get("added", win.get("added", [])))
    errors.extend(add_errors)
    if not errors:
        rec = apply(base_rec, clean, added)
        errors = check_window_record(rec, f"window {win['window_index']}")
    return errors, clean, added


def log_changes(win: dict[str, Any], clean: list[dict[str, Any]], added: list[dict[str, Any]], reviewed: bool,
                at: str) -> list[dict[str, Any]]:
    entries = []
    for old, new in zip(win["concepts"], clean):
        for field in ("decision", "label", "reason"):
            if old[field] != new[field]:
                entries.append({"at": at, "window_index": win["window_index"], "v1_label": new["v1_label"],
                                "field": field, "before": old[field], "after": new[field], "reason": new["reason"]})
    old_added = {a["id"]: a for a in win.get("added", [])}
    new_added = {a["id"]: a for a in added}
    for aid, a in new_added.items():
        old = old_added.get(aid)
        if old is None:
            entries.append({"at": at, "window_index": win["window_index"], "v1_label": None, "added_id": aid,
                            "field": "added", "before": None, "after": {"label": a["label"], "aliases": a["aliases"]},
                            "reason": a["reason"]})
            continue
        for field in ("label", "aliases", "reason"):
            if old[field] != a[field]:
                entries.append({"at": at, "window_index": win["window_index"], "v1_label": None, "added_id": aid,
                                "field": f"added_{field}", "before": old[field], "after": a[field],
                                "reason": a["reason"]})
    for aid, old in old_added.items():
        if aid not in new_added:
            entries.append({"at": at, "window_index": win["window_index"], "v1_label": None, "added_id": aid,
                            "field": "added", "before": {"label": old["label"], "aliases": old["aliases"]},
                            "after": None, "reason": old["reason"]})
    if win["reviewed"] != reviewed:
        entries.append({"at": at, "window_index": win["window_index"], "v1_label": None, "field": "reviewed",
                        "before": win["reviewed"], "after": reviewed, "reason": ""})
    return entries


def update_window(state: dict[str, Any], base: dict[str, Any], window_index: int, body: Any,
                  at: str | None = None) -> list[str]:
    """Apply one window's decisions to the state (in memory) and append the changes to its log. Returns errors; on
    errors the state is unchanged."""
    win = next((w for w in state["windows"] if w["window_index"] == window_index), None)
    base_rec = next((r for r in base["windows"] if r["window"]["window_index"] == window_index), None)
    if win is None or base_rec is None:
        return [f"window {window_index} is not a gold window"]
    errors, clean, added = check_payload(win, base_rec, body)
    if errors:
        return errors
    state["log"].extend(log_changes(win, clean, added, body["reviewed"], at or now_utc()))
    win["concepts"], win["added"], win["reviewed"] = clean, added, body["reviewed"]
    return []


# -- status and merge -----------------------------------------------------------------------------------------------


def derived(state: dict[str, Any], base: dict[str, Any]) -> dict[int, dict[str, Any]]:
    recs = {r["window"]["window_index"]: r for r in base["windows"]}
    return {w["window_index"]: apply(recs[w["window_index"]], w["concepts"], w.get("added", []))
            for w in state["windows"]}


def variant_key(label: str) -> tuple[str, ...]:
    words = [w for w in re.findall(r"\w+", label.casefold()) if w not in VARIANT_STOPWORDS]
    return tuple(sorted(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words))


def labels_in_use(recs: dict[int, dict[str, Any]]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, rec in sorted(recs.items()):
        for c in rec["concepts"]:
            out.setdefault(c["label"], []).append(i)
    return dict(sorted(out.items(), key=lambda kv: kv[0].casefold()))


def possible_variants(labels: dict[str, list[int]]) -> list[list[str]]:
    """Groups of different labels that are the same apart from case, punctuation, a plural s or small words: they
    may name one concept and so need one canonical name. Only a hint: two of them may be different concepts."""
    groups: dict[tuple[str, ...], list[str]] = {}
    for label in labels:
        groups.setdefault(variant_key(label), []).append(label)
    return [g for g in groups.values() if len(g) > 1]


def summary(state: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    recs = derived(state, base)
    concepts = [c for w in state["windows"] for c in w["concepts"]]
    labels = labels_in_use(recs)
    return {
        "windows": len(state["windows"]),
        "reviewed": sum(w["reviewed"] for w in state["windows"]),
        "not_reviewed": [w["window_index"] for w in state["windows"] if not w["reviewed"]],
        "concepts_v1": len(concepts),
        "kept": sum(c["decision"] == "keep" for c in concepts),
        "renamed": sum(c["decision"] == "keep" and c["label"] != c["v1_label"] for c in concepts),
        "removed": sum(c["decision"] == "remove" for c in concepts),
        "undecided": sum(c["decision"] is None for c in concepts),
        "added": sum(len(w.get("added", [])) for w in state["windows"]),
        "concepts_v2": sum(len(r["concepts"]) for r in recs.values()),
        "relations_v2": sum(len(r["relations"]) for r in recs.values()),
        "log_entries": len(state["log"]),
        "labels_in_use": labels,
        "possible_variants": possible_variants(labels),
    }


def merged(state: dict[str, Any], base: dict[str, Any], producer_name: str) -> dict[str, Any]:
    not_done = [w["window_index"] for w in state["windows"] if not w["reviewed"]]
    if not_done:
        raise SystemExit(f"{len(not_done)} window(s) not marked reviewed yet: {not_done}")
    recs = derived(state, base)
    gold = {"schema_version": base["schema_version"], "lecture_id": base["lecture_id"],
            "producer": {"kind": "human", "name": producer_name},
            "sample_manifest_sha256": base["sample_manifest_sha256"],
            "windows": [recs[r["window"]["window_index"]] for r in base["windows"]]}
    errors = check_document(gold)
    if errors:
        raise SystemExit("the new gold is invalid:\n  - " + "\n  - ".join(errors))
    return gold
