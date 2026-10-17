"""Blind adjudication sheet and the append-only adjudications file (ADR-0048 section 4).

Sheet. For one comparison, every model concept that the string rule leaves unmatched, in every arm being compared, is
pooled. Duplicates are removed: the same window and the same normalised label count once, whichever arms produced
them (the entry shows the union of their aliases and the alphabetically first spelling of the label, so no arm's
form is preferred). Concepts that already have a decision in adjudications.json are left out: decisions are frozen
and reused by every later run. The entries are shuffled with a recorded seed. No entry says which arm produced it;
the sheet file records its input files only for audit, and the terminal session never shows them.

Decisions. `record_decisions` walks the sheet in its shuffled order and asks, per entry, which gold concept of that
window the model concept is (a number) or that it matches none (`n`). Each answer is appended to adjudications.json
at once (atomic rewrite of the file with one more entry). An existing entry is never changed or removed; a second
decision for the same key is refused.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from extraction_schema import normalise
from matching import ADJUDICATION_VERSION, Adjudications, load_adjudications, match_window
from scoring import EMPTY, ArmRun, sha256_file

SHEET_VERSION = 1


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_sheet(lecture_id: str, comparison: str, gold: dict[str, Any], gold_sha256: str, arms: list[ArmRun],
                adjudications: Adjudications, seed: int | None = None) -> dict[str, Any]:
    seed = secrets.randbelow(2**31) if seed is None else seed
    pooled: dict[tuple[int, str], dict[str, Any]] = {}
    for arm in arms:
        records = {r["window"]["window_index"]: r for r in arm.doc.get("windows", [])}
        for g in gold["windows"]:
            i = g["window"]["window_index"]
            score = match_window(records.get(i, EMPTY), g, i, None)
            for c in score.unmatched_pred:
                key = (i, normalise(c["label"]))
                if key in adjudications:
                    continue
                e = pooled.setdefault(key, {"window_index": i, "start_s": g["window"]["start_s"],
                                            "end_s": g["window"]["end_s"], "labels": set(), "aliases": set(),
                                            "gold_concepts": [{"label": x["label"], "aliases": list(x["aliases"])}
                                                              for x in g["concepts"]]})
                e["labels"].add(c["label"])
                e["aliases"].update(c.get("aliases", []))
    entries = []
    for key in sorted(pooled):  # a fixed order before the seeded shuffle, so the seed alone fixes the sheet
        e = pooled[key]
        label = min(e["labels"])
        entries.append({"window_index": e["window_index"], "start_s": e["start_s"], "end_s": e["end_s"],
                        "model_label": label,
                        "model_aliases": sorted(a for a in e["aliases"] if normalise(a) != key[1]),
                        "gold_concepts": e["gold_concepts"]})
    random.Random(seed).shuffle(entries)
    for n, e in enumerate(entries, 1):
        e["entry"] = n
    return {
        "sheet_version": SHEET_VERSION,
        "lecture_id": lecture_id,
        "comparison": comparison,
        "seed": seed,
        "created_at": now_utc(),
        "gold_sha256": gold_sha256,
        "inputs": sorted(arm.doc_sha256 for arm in arms),  # extraction.json hashes, sorted: no arm order or name
        "adjudications_entries_before": len(adjudications),
        "entries": entries,
    }


# -- adjudications file ----------------------------------------------------------------------------------------------


def empty_adjudications(lecture_id: str) -> dict[str, Any]:
    return {"adjudication_version": ADJUDICATION_VERSION, "lecture_id": lecture_id, "entries": []}


def read_adjudications_doc(path: Path, lecture_id: str) -> dict[str, Any]:
    if not path.is_file():
        return empty_adjudications(lecture_id)
    load_adjudications(path, lecture_id)  # version, lecture and conflict checks
    return json.loads(path.read_text(encoding="utf-8"))


def append_adjudication(path: Path, lecture_id: str, entry: dict[str, Any]) -> None:
    """Append one decision. Refuses a key that already has an entry (entries are frozen once made)."""
    doc = read_adjudications_doc(path, lecture_id)
    key = (int(entry["window_index"]), normalise(entry["model_label"]))
    for e in doc["entries"]:
        if (int(e["window_index"]), normalise(e["model_label"])) == key:
            raise ValueError(f"window {key[0]} label {entry['model_label']!r} already has a decision; entries are "
                             "append-only and never changed")
    doc["entries"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def check_sheet(sheet: dict[str, Any], lecture_id: str, gold_sha256: str) -> None:
    if sheet.get("sheet_version") != SHEET_VERSION or sheet.get("lecture_id") != lecture_id:
        raise SystemExit(f"not a version {SHEET_VERSION} adjudication sheet for {lecture_id}")
    if sheet["gold_sha256"] != gold_sha256:
        raise SystemExit("gold.json changed since this sheet was made; make a new sheet")


def format_entry(e: dict[str, Any], total: int) -> str:
    def names(c: dict[str, Any]) -> str:
        return c["label"] + (f"  (also: {', '.join(c['aliases'])})" if c["aliases"] else "")

    lines = [f"\nEntry {e['entry']} of {total}: window {e['window_index']} ({e['start_s']:.0f}-{e['end_s']:.0f} s)",
             f"  model concept: {names({'label': e['model_label'], 'aliases': e['model_aliases']})}",
             "  gold concepts of this window:"]
    lines += [f"    {k}. {names(c)}" for k, c in enumerate(e["gold_concepts"], 1)] or ["    (none)"]
    return "\n".join(lines)


def record_decisions(sheet: dict[str, Any], sheet_sha256: str, path: Path, decided_by: str,
                     ask: Callable[[str], str] | None = None, say: Callable[[str], None] | None = None
                     ) -> dict[str, int]:
    """Interactive pass over the undecided entries. Answers: a gold concept's number, `n` (no match), `s` (skip for
    now), `q` (stop). Returns counts of what was recorded."""
    ask, say = ask or input, say or print
    lecture_id = sheet["lecture_id"]
    done = load_adjudications(path, lecture_id) if path.is_file() else {}
    todo = [e for e in sheet["entries"] if (e["window_index"], normalise(e["model_label"])) not in done]
    counts = {"match": 0, "no_match": 0, "skipped": 0, "remaining": len(todo)}
    say(f"{len(todo)} of {len(sheet['entries'])} entries need a decision. Answer with a gold concept's number, "
        "n = no match, s = skip, q = quit. Decisions are final once recorded.")
    for e in todo:
        say(format_entry(e, len(sheet["entries"])))
        while True:
            ans = ask("  decision> ").strip().lower()
            if ans == "q":
                return counts
            if ans == "s":
                counts["skipped"] += 1
                break
            if ans == "n":
                gold_label = None
            elif ans.isdigit() and 1 <= int(ans) <= len(e["gold_concepts"]):
                gold_label = e["gold_concepts"][int(ans) - 1]["label"]
            else:
                say("  answer with a listed number, n, s or q")
                continue
            append_adjudication(path, lecture_id, {
                "window_index": e["window_index"], "model_label": e["model_label"], "gold_label": gold_label,
                "decided_by": decided_by, "decided_at": now_utc(), "sheet_sha256": sheet_sha256,
            })
            counts["no_match" if gold_label is None else "match"] += 1
            counts["remaining"] -= 1
            break
    return counts


def load_sheet(path: Path) -> tuple[dict[str, Any], str]:
    return json.loads(path.read_text(encoding="utf-8")), sha256_file(path)
