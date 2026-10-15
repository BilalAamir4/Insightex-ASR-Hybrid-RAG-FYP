"""M7 extraction schema v1 (ADR-0048): validator and the label normalisation used for concept matching.

One record per 30 s grid window (ADR-0045). The same shape holds human gold labels and model output, so a gold file
and a model run are scored by the same rules. The JSON Schema is `extraction.schema.json` next to this file; this
module checks everything that schema checks (standard library only, no jsonschema dependency) plus the rules a JSON
Schema cannot state: relation endpoints are concept labels of the same window, no two concepts share a normalised
name, no duplicate relations, no self-relations, end_s > start_s, unique window_index, and every window's lecture_id
equals the document's.

Two byte-identical copies exist: backend/src/insightex/extract/extraction_schema.py (production, imported by the
extraction stage) and tools/label_concepts/extraction_schema.py (tools are standalone and never import backend/).
backend/tests/unit/test_extraction_schema.py fails if the copies, or the two JSON Schema files, differ.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("extraction.schema.json")
RELATION_TYPES = ("prerequisite_of", "part_of", "example_of", "contrasts_with")
SYMMETRIC_TYPES = frozenset({"contrasts_with"})
PRODUCER_KINDS = ("human", "model")
NAME_MAX = 200  # characters; labels, aliases, ids and names (matches $defs/nonblank)
CUE_MAX = 300  # characters
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def normalise(text: str) -> str:
    """Matching form of a label or alias (ADR-0048): NFKC, case-folded, with every punctuation character (Unicode
    category P*), whitespace or separator (Z*, str.isspace) and invisible format character (Cf, e.g. the zero-width
    non-joiner used in Urdu script) removed. "K-Means", "k means" and "kmeans" all normalise to "kmeans"."""
    out = []
    for ch in unicodedata.normalize("NFKC", text).casefold():
        cat = unicodedata.category(ch)
        if ch.isspace() or cat[0] in ("P", "Z") or cat == "Cf":
            continue
        out.append(ch)
    return "".join(out)


def relation_key(head: str, rtype: str, tail: str) -> tuple[str, str, str]:
    """Identity of a relation: direction counts except for the symmetric contrasts_with."""
    if rtype in SYMMETRIC_TYPES and tail < head:
        head, tail = tail, head
    return (head, rtype, tail)


# -- structural checks (mirror extraction.schema.json) ------------------------------------------------------------


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _nonblank(v: Any, where: str, errors: list[str], max_len: int = NAME_MAX) -> bool:
    if not isinstance(v, str):
        errors.append(f"{where}: must be a string")
        return False
    if not v.strip():
        errors.append(f"{where}: must not be empty or blank")
        return False
    if len(v) > max_len:
        errors.append(f"{where}: longer than {max_len} characters")
        return False
    return True


def _keys(obj: Any, where: str, required: tuple[str, ...], optional: tuple[str, ...], errors: list[str]) -> bool:
    if not isinstance(obj, dict):
        errors.append(f"{where}: must be an object")
        return False
    for k in required:
        if k not in obj:
            errors.append(f"{where}: missing field {k!r}")
    for k in obj:
        if k not in required and k not in optional:
            errors.append(f"{where}: unknown field {k!r}")
    return True


def _check_window_ref(ref: Any, where: str, errors: list[str]) -> None:
    if not _keys(ref, where, ("lecture_id", "window_index", "start_s", "end_s"), (), errors):
        return
    if "lecture_id" in ref:
        _nonblank(ref["lecture_id"], f"{where}.lecture_id", errors)
    if "window_index" in ref and not (_is_int(ref["window_index"]) and ref["window_index"] >= 0):
        errors.append(f"{where}.window_index: must be an integer >= 0")
    for k in ("start_s", "end_s"):
        if k in ref and not (_is_num(ref[k]) and ref[k] >= 0):
            errors.append(f"{where}.{k}: must be a number >= 0")
    if _is_num(ref.get("start_s")) and _is_num(ref.get("end_s")) and ref["end_s"] <= ref["start_s"]:
        errors.append(f"{where}: end_s must be greater than start_s")


def check_labels(rec: Any, where: str = "window") -> list[str]:
    """Errors in the labelled part of one window record (concepts, relations, important, cue, is_recap), structural
    and semantic. The `window` reference is checked by check_window_record."""
    errors: list[str] = []
    if not isinstance(rec, dict):
        return [f"{where}: must be an object"]
    concepts = rec.get("concepts")
    labels: list[str] = []
    owner: dict[str, str] = {}  # normalised name -> label of the concept that owns it
    if not isinstance(concepts, list):
        errors.append(f"{where}.concepts: must be a list")
        concepts = []
    for i, c in enumerate(concepts):
        cw = f"{where}.concepts[{i}]"
        if not _keys(c, cw, ("label", "aliases"), (), errors):
            continue
        ok_label = "label" in c and _nonblank(c["label"], f"{cw}.label", errors)
        aliases = c.get("aliases", [])
        if not isinstance(aliases, list):
            errors.append(f"{cw}.aliases: must be a list")
            aliases = []
        names = [c["label"]] if ok_label else []
        for j, a in enumerate(aliases):
            if _nonblank(a, f"{cw}.aliases[{j}]", errors):
                names.append(a)
        if ok_label:
            labels.append(c["label"])
        seen_here: set[str] = set()
        for name in names:
            key = normalise(name)
            if not key:
                errors.append(f"{cw}: {name!r} has no letters or digits after normalisation")
                continue
            if key in seen_here:
                errors.append(f"{cw}: {name!r} repeats a name of the same concept (after normalisation)")
                continue
            seen_here.add(key)
            if key in owner:
                errors.append(f"{cw}: {name!r} is also a name of concept {owner[key]!r} (after normalisation)")
            else:
                owner[key] = c.get("label", "?")
    relations = rec.get("relations")
    if not isinstance(relations, list):
        errors.append(f"{where}.relations: must be a list")
        relations = []
    label_set = set(labels)
    seen_rel: set[tuple[str, str, str]] = set()
    for i, r in enumerate(relations):
        rw = f"{where}.relations[{i}]"
        if not _keys(r, rw, ("head", "type", "tail"), (), errors):
            continue
        ok = True
        for end in ("head", "tail"):
            if end in r and _nonblank(r[end], f"{rw}.{end}", errors):
                if r[end] not in label_set:
                    errors.append(f"{rw}.{end}: {r[end]!r} is not the label of a concept in this window")
                    ok = False
            else:
                ok = False
        if r.get("type") not in RELATION_TYPES:
            errors.append(f"{rw}.type: must be one of {', '.join(RELATION_TYPES)}")
            ok = False
        if ok:
            if r["head"] == r["tail"]:
                errors.append(f"{rw}: head and tail are the same concept")
                continue
            key = relation_key(r["head"], r["type"], r["tail"])
            if key in seen_rel:
                errors.append(f"{rw}: duplicate relation")
            seen_rel.add(key)
    if "important" not in rec or not isinstance(rec["important"], bool):
        errors.append(f"{where}.important: must be true or false")
    if "cue" not in rec:
        errors.append(f"{where}: missing field 'cue'")
    elif rec.get("important") is True:
        _nonblank(rec["cue"], f"{where}.cue", errors, CUE_MAX)
    elif rec.get("important") is False and rec["cue"] is not None:
        errors.append(f"{where}.cue: must be null when important is false")
    if "is_recap" in rec and not isinstance(rec["is_recap"], bool):
        errors.append(f"{where}.is_recap: must be true or false")
    return errors


def check_window_record(rec: Any, where: str = "window") -> list[str]:
    errors: list[str] = []
    if not _keys(rec, where, ("window", "concepts", "relations", "important", "cue"), ("is_recap",), errors):
        return errors
    if "window" in rec:
        _check_window_ref(rec["window"], f"{where}.window", errors)
    return errors + check_labels(rec, where)


def check_document(doc: Any) -> list[str]:
    """All errors in an extraction document; an empty list means valid."""
    errors: list[str] = []
    if not _keys(doc, "document", ("schema_version", "lecture_id", "producer", "windows"), ("sample_manifest_sha256",),
                 errors):
        return errors
    if "schema_version" in doc and (doc["schema_version"] != SCHEMA_VERSION or not _is_int(doc["schema_version"])):
        errors.append(f"document.schema_version: must be {SCHEMA_VERSION}")
    if "lecture_id" in doc:
        _nonblank(doc["lecture_id"], "document.lecture_id", errors)
    if "producer" in doc and _keys(doc["producer"], "document.producer", ("kind", "name"), (), errors):
        if "kind" in doc["producer"] and doc["producer"]["kind"] not in PRODUCER_KINDS:
            errors.append(f"document.producer.kind: must be one of {', '.join(PRODUCER_KINDS)}")
        if "name" in doc["producer"]:
            _nonblank(doc["producer"]["name"], "document.producer.name", errors)
    if "sample_manifest_sha256" in doc and not (isinstance(doc["sample_manifest_sha256"], str)
                                                and _SHA256.match(doc["sample_manifest_sha256"])):
        errors.append("document.sample_manifest_sha256: must be 64 lowercase hex characters")
    windows = doc.get("windows")
    if not isinstance(windows, list):
        errors.append("document.windows: must be a list")
        return errors
    seen: set[int] = set()
    for i, rec in enumerate(windows):
        errors += check_window_record(rec, f"windows[{i}]")
        ref = rec.get("window") if isinstance(rec, dict) else None
        if isinstance(ref, dict):
            idx = ref.get("window_index")
            if _is_int(idx):
                if idx in seen:
                    errors.append(f"windows[{i}]: window_index {idx} appears more than once")
                seen.add(idx)
            if isinstance(doc.get("lecture_id"), str) and ref.get("lecture_id") != doc["lecture_id"]:
                errors.append(f"windows[{i}].window.lecture_id: differs from document.lecture_id")
    return errors
