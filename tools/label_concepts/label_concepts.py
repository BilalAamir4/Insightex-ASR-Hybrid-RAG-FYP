"""M7 gold-label tool (ADR-0048): sample windows, label them in a browser, validate, measure agreement, merge.

Standalone: imports nothing from backend/. Rules for labellers: docs/labelling/m7_concepts.md.

  python label_concepts.py sample    --lecture <id> [--n 40] [--shared 10] [--seed 7] [--labellers bilal ...]
                                     [--exclude I=REASON ...]
  python label_concepts.py reassign  --lecture <id> --labellers <name> [<name> ...] --note TEXT
  python label_concepts.py serve     --lecture <id> --labeller <name> [--port 8765]
  python label_concepts.py validate  --lecture <id> --labeller <name>
  python label_concepts.py agreement --lecture <id> --a <name> --b <name> [--adjudications FILE]
  python label_concepts.py merge     --lecture <id>

Session 2 (scoring model runs written by `insightex extract-eval run`; scoring.py, adjudication.py):

  python label_concepts.py adjudication-sheet --lecture <id> --comparison C1 --arm NAME=RUN_DIR ... [--seed N]
  python label_concepts.py adjudicate         --lecture <id> --sheet FILE [--by bilal]
  python label_concepts.py score              --lecture <id> --arm NAME=RUN_DIR ... [--out FILE]
  python label_concepts.py compare            --lecture <id> --comparison C1 --a NAME=RUN_DIR --b NAME=RUN_DIR
                                              [--out FILE]

Files live in tools/label_concepts/labels/<lecture_id>/: sample.json (the manifest), <labeller>.json (labels, one
extraction document per labeller; <labeller>_repeat.json for the blind repeat of the shared windows),
agreement_<a>_<b>.json, gold.json, adjudications.json (append-only), adjudication_sheets/<comparison>-<time>.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extraction_schema import check_document
from grid import Workspace, check_against_index, data_dir, lecture_grid
from matching import load_adjudications, match_window, micro
from sampling import accepted_manifest_sha256, build_manifest, reassign_manifest, windows_for

LABELS_ROOT = Path(__file__).resolve().parent / "labels"
DEFAULT_LABELLERS = ("bilal",)  # single labeller (ADR-0048 Amendment 1)


def lecture_dir(lecture_id: str, root: Path | None = None) -> Path:
    return (root or LABELS_ROOT) / lecture_id


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_manifest(lecture_id: str, root: Path | None = None) -> tuple[dict[str, Any], str]:
    path = lecture_dir(lecture_id, root) / "sample.json"
    if not path.is_file():
        raise SystemExit(f"no sample manifest at {path}; run `sample` first")
    return json.loads(path.read_text(encoding="utf-8")), sha256_file(path)


def parse_excludes(items: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for item in items:
        idx, sep, reason = item.partition("=")
        if not sep or not idx.strip().isdigit() or not reason.strip():
            raise SystemExit(f"--exclude takes WINDOW_INDEX=REASON, got {item!r}")
        out[int(idx)] = reason.strip()
    return out


# -- sample -------------------------------------------------------------------------------------------------------


def cmd_sample(a: argparse.Namespace) -> int:
    out = lecture_dir(a.lecture, a.labels_root) / "sample.json"
    if out.exists() and not a.force:
        raise SystemExit(f"{out} exists; labels may depend on it. Pass --force only if no labelling has started.")
    ws = Workspace(data_dir(a.data_dir), a.lecture)
    windows, info = lecture_grid(ws)
    if info["language_tier_at_processing"] != "tested" and not a.allow_untested:
        raise SystemExit(f"{a.lecture} was transcribed with an untested language ({info['language_id']}); untested "
                         "lectures are excluded from evaluation (ADR-0040). --allow-untested overrides for trials.")
    index_check = check_against_index(ws, windows)
    manifest = build_manifest(
        lecture_id=a.lecture, windows=windows, transcript_info=info, index_check=index_check, seed=a.seed, n=a.n,
        n_shared=a.shared, labellers=a.labellers, excluded=parse_excludes(a.exclude),
        created_at=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    write_json(out, manifest)
    print(f"wrote {out}")
    print(f"{manifest['n_windows_total']} windows, {len(manifest['excluded'])} excluded, {manifest['n_eligible']} "
          f"eligible; sampled {manifest['n_sampled']} (seed {a.seed}), {a.shared} shared; grid vs index: {index_check}")
    if manifest["census"]:
        print(f"census: {manifest['census_note']}")
    for lab in a.labellers:
        print(f"  {lab}: {len(windows_for(manifest, lab))} windows")
    return 0


# -- reassign -----------------------------------------------------------------------------------------------------


def cmd_reassign(a: argparse.Namespace) -> int:
    out = lecture_dir(a.lecture, a.labels_root) / "sample.json"
    manifest, msha = load_manifest(a.lecture, a.labels_root)
    try:
        new = reassign_manifest(manifest, msha, a.labellers, a.note, dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    except ValueError as e:
        raise SystemExit(str(e)) from e
    write_json(out, new)
    print(f"wrote {out} (previous sha256 {msha} recorded under amendments)")
    for lab in a.labellers:
        print(f"  {lab}: {len(windows_for(new, lab))} windows; newly assigned "
              f"{new['amendments'][-1]['newly_assigned'][lab]}")
    return 0


# -- serve --------------------------------------------------------------------------------------------------------


def cmd_serve(a: argparse.Namespace) -> int:
    from server import LabelStore, serve

    manifest, msha = load_manifest(a.lecture, a.labels_root)
    rows = windows_for(manifest, a.labeller)
    ws = Workspace(data_dir(a.data_dir), a.lecture)
    grid, info = lecture_grid(ws)
    if info["asr_key"] != manifest["transcript"]["asr_key"]:
        raise SystemExit("the lecture's transcript changed since the sample was drawn (asr stage key differs)")
    by_index = {w.index: w for w in grid}
    windows = []
    for r in rows:
        w = by_index.get(r["window_index"])
        if w is None or w.text_sha256 != r["text_sha256"] or (w.start_s, w.end_s) != (r["start_s"], r["end_s"]):
            raise SystemExit(f"window {r['window_index']} no longer matches the sample manifest")
        windows.append({**{k: r[k] for k in ("window_index", "start_s", "end_s", "shared")}, "text": w.text})
    store = LabelStore(lecture_dir(a.lecture, a.labels_root) / f"{a.labeller}.json", a.lecture, a.labeller, msha, rows,
                       frozenset(accepted_manifest_sha256(manifest, msha)))
    serve(port=a.port, session={"lecture_id": a.lecture, "labeller": a.labeller, "windows": windows}, rows=rows,
          store=store, video=ws.video())
    return 0


# -- validate -----------------------------------------------------------------------------------------------------


def validate_labels(doc: Any, manifest: dict[str, Any], manifest_sha256: str, labeller: str,
                    complete: bool = True) -> list[str]:
    """Schema errors plus checks against the sample manifest. complete=False skips the 'all windows present' check."""
    errors = check_document(doc)
    if errors:
        return errors
    if doc["lecture_id"] != manifest["lecture_id"]:
        errors.append(f"lecture_id {doc['lecture_id']!r} is not the manifest's {manifest['lecture_id']!r}")
    if doc["producer"] != {"kind": "human", "name": labeller}:
        errors.append(f"producer must be {{'kind': 'human', 'name': {labeller!r}}}")
    if doc.get("sample_manifest_sha256") not in accepted_manifest_sha256(manifest, manifest_sha256):
        errors.append("sample_manifest_sha256 matches neither the current sample.json nor one it was amended from")
    rows = {r["window_index"]: r for r in manifest["windows"]}
    expected = {r["window_index"] for r in windows_for(manifest, labeller)}
    present = set()
    for rec in doc["windows"]:
        ref = rec["window"]
        i = ref["window_index"]
        present.add(i)
        if i not in rows:
            errors.append(f"window {i} is not in the sample")
        elif i not in expected:
            errors.append(f"window {i} is not assigned to {labeller}")
        elif (ref["start_s"], ref["end_s"]) != (rows[i]["start_s"], rows[i]["end_s"]):
            errors.append(f"window {i}: start/end differ from the sample manifest")
    missing = sorted(expected - present, key=lambda i: rows[i]["order"])
    if complete and missing:
        errors.append(f"{len(missing)} assigned window(s) not labelled yet: {missing}")
    return errors


def load_labels(lecture_id: str, labeller: str, root: Path | None = None) -> tuple[dict[str, Any], Path]:
    path = lecture_dir(lecture_id, root) / f"{labeller}.json"
    if not path.is_file():
        raise SystemExit(f"no labels file at {path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def cmd_validate(a: argparse.Namespace) -> int:
    manifest, msha = load_manifest(a.lecture, a.labels_root)
    doc, path = load_labels(a.lecture, a.labeller, a.labels_root)
    errors = validate_labels(doc, manifest, msha, a.labeller)
    if errors:
        print(f"{path}: {len(errors)} problem(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"{path}: valid, {len(doc['windows'])} windows")
    return 0


# -- agreement ----------------------------------------------------------------------------------------------------


def agreement(doc_a: dict[str, Any], doc_b: dict[str, Any], manifest: dict[str, Any],
              adjudications: dict | None = None) -> dict[str, Any]:
    """B scored against A on the shared windows (A is the reference: P is B's precision, R its recall)."""
    shared = [r for r in manifest["windows"] if r["shared"]]
    recs_a = {r["window"]["window_index"]: r for r in doc_a["windows"]}
    recs_b = {r["window"]["window_index"]: r for r in doc_b["windows"]}
    missing = [r["window_index"] for r in shared if r["window_index"] not in recs_a or r["window_index"] not in recs_b]
    if missing:
        raise SystemExit(f"shared windows not labelled by both: {missing}")
    scores = [match_window(recs_b[r["window_index"]], recs_a[r["window_index"]], r["window_index"], adjudications)
              for r in shared]
    per_window = []
    for r, s in zip(shared, scores):
        per_window.append({
            "window_index": s.window_index, "start_s": r["start_s"],
            "concepts_a": s.concept_ref, "concepts_b": s.concept_pred, "concepts_matched": s.concept_tp,
            "concept_f1": s.concept_f1,
            "relations_a": s.relation_ref, "relations_b": s.relation_pred, "relations_matched": s.relation_tp,
            "relation_f1": s.relation_f1,
            "important_a": s.important_ref, "important_b": s.important_pred,
            "matched_pairs": [{"b": p, "a": q, "by": how} for p, q, how in s.pairs],
            "only_a": [c["label"] for c in s.unmatched_ref],
            "only_b": [c["label"] for c in s.unmatched_pred],
        })
    return {"per_window": per_window, "micro": micro(scores)}


def fmt_ratio(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def cmd_agreement(a: argparse.Namespace) -> int:
    manifest, msha = load_manifest(a.lecture, a.labels_root)
    docs, paths = {}, {}
    for name in (a.a, a.b):
        doc, path = load_labels(a.lecture, name, a.labels_root)
        errors = validate_labels(doc, manifest, msha, name, complete=False)
        if errors:
            raise SystemExit(f"{path} is invalid; run validate first:\n  - " + "\n  - ".join(errors))
        docs[name], paths[name] = doc, path
    adj = load_adjudications(Path(a.adjudications), a.lecture) if a.adjudications else None
    result = agreement(docs[a.a], docs[a.b], manifest, adj)
    print(f"Agreement on {len(result['per_window'])} shared windows of {a.lecture}: A = {a.a}, B = {a.b}"
          f"{' (with adjudications)' if adj is not None else ' (string rule only)'}")
    print(f"{'win':>4} {'start':>6} {'cA':>3} {'cB':>3} {'cM':>3} {'cF1':>6} {'rA':>3} {'rB':>3} {'rM':>3} {'rF1':>6}"
          f" {'impA':>5} {'impB':>5}")
    for w in result["per_window"]:
        print(f"{w['window_index']:>4} {w['start_s']:>6.0f} {w['concepts_a']:>3} {w['concepts_b']:>3} "
              f"{w['concepts_matched']:>3} {w['concept_f1']:>6.3f} {w['relations_a']:>3} {w['relations_b']:>3} "
              f"{w['relations_matched']:>3} {w['relation_f1']:>6.3f} {w['important_a']!s:>5} "
              f"{w['important_b']!s:>5}")
    m = result["micro"]
    for part in ("concept", "relation"):
        x = m[part]
        print(f"micro {part}: matched {x['tp']}, A {x['ref']}, B {x['pred']}; P {fmt_ratio(x['precision'])} "
              f"R {fmt_ratio(x['recall'])} F1 {x['f1']:.3f}")
    imp = m["important"]
    print(f"important: same flag in {fmt_ratio(imp['agreement'])} of windows; A true {imp['ref']}, B true "
          f"{imp['pred']}, both {imp['tp']}; P {fmt_ratio(imp['precision'])} R {fmt_ratio(imp['recall'])}")
    print("\nTo discuss (concepts only one labeller has):")
    for w in result["per_window"]:
        if w["only_a"] or w["only_b"]:
            print(f"  window {w['window_index']}: only {a.a}: {w['only_a']}; only {a.b}: {w['only_b']}")
    report = {
        "lecture_id": a.lecture, "a": a.a, "b": a.b, "sample_manifest_sha256": msha,
        "inputs": {name: {"path": str(paths[name].relative_to(LABELS_ROOT.parent)) if paths[name].is_relative_to(
            LABELS_ROOT.parent) else str(paths[name]), "sha256": sha256_file(paths[name])} for name in (a.a, a.b)},
        "adjudications": a.adjudications, "rule": "ADR-0048 concept and relation matching", **result,
    }
    out = lecture_dir(a.lecture, a.labels_root) / f"agreement_{a.a}_{a.b}.json"
    write_json(out, report)
    print(f"\nwrote {out}")
    return 0


# -- merge --------------------------------------------------------------------------------------------------------


def cmd_merge(a: argparse.Namespace) -> int:
    """gold.json. One labeller (ADR-0048 Amendment 1): every window from that labeller's (revised) file. Two or more:
    the shared windows from consensus.json, every other window from the labeller it is assigned to."""
    manifest, msha = load_manifest(a.lecture, a.labels_root)
    single = len(manifest["labellers"]) == 1
    sources: dict[str, dict[int, dict[str, Any]]] = {}
    for name in manifest["labellers"] if single else [*manifest["labellers"], "consensus"]:
        doc, path = load_labels(a.lecture, name, a.labels_root)
        errors = validate_labels(doc, manifest, msha, name)
        if errors:
            raise SystemExit(f"{path} is invalid or incomplete; run validate:\n  - " + "\n  - ".join(errors))
        sources[name] = {r["window"]["window_index"]: r for r in doc["windows"]}
    windows = []
    for r in manifest["windows"]:
        src = "consensus" if r["shared"] and not single else r["assigned_to"][0]
        windows.append(sources[src][r["window_index"]])
    name = (f"gold: {manifest['labellers'][0]} (single annotator)" if single
            else "gold: consensus (shared) + " + " + ".join(manifest["labellers"]))
    gold = {"schema_version": 1, "lecture_id": a.lecture, "producer": {"kind": "human", "name": name},
            "sample_manifest_sha256": msha, "windows": windows}
    errors = check_document(gold)
    if errors:
        raise SystemExit("merged gold is invalid:\n  - " + "\n  - ".join(errors))
    out = lecture_dir(a.lecture, a.labels_root) / "gold.json"
    write_json(out, gold)
    print(f"wrote {out}: {len(windows)} windows")
    return 0


# -- Session 2: adjudication, scoring, comparison -------------------------------------------------------------------


def gold_path(lecture_id: str, root: Path | None = None) -> Path:
    return lecture_dir(lecture_id, root) / "gold.json"


def adjudications_path(lecture_id: str, root: Path | None = None) -> Path:
    return lecture_dir(lecture_id, root) / "adjudications.json"


def load_arms(specs: list[str]) -> list[Any]:
    from scoring import load_arm_run, parse_arm

    arms = [load_arm_run(*parse_arm(s)) for s in specs]
    if len({a.name for a in arms}) != len(arms):
        raise SystemExit("arm names must differ")
    return arms


def consistency(lecture_id: str, root: Path | None = None) -> dict[str, Any]:
    """ADR-0048 Amendment 1/2: single-annotator intra-rater consistency, `<labeller>` (finished) against
    `<labeller>_repeat` on the shared windows, string rule only. Never an inter-annotator ceiling."""
    manifest, msha = load_manifest(lecture_id, root)
    if len(manifest["labellers"]) != 1:
        return {"available": False, "reason": "two-labeller manifest: use `agreement` for the human ceiling"}
    name = manifest["labellers"][0]
    docs = {}
    for lab in (name, f"{name}_repeat"):
        path = lecture_dir(lecture_id, root) / f"{lab}.json"
        if not path.is_file():
            return {"available": False, "reason": f"{path.name} does not exist yet"}
        doc = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_labels(doc, manifest, msha, lab)
        if errors:
            return {"available": False, "reason": f"{path.name} is invalid or incomplete ({len(errors)} problem(s))"}
        docs[lab] = (doc, sha256_file(path))
    result = agreement(docs[name][0], docs[f"{name}_repeat"][0], manifest, None)
    return {
        "available": True,
        "kind": f"single-annotator intra-rater consistency ({name} vs {name}_repeat, string rule only); not an "
                "inter-annotator ceiling",
        "windows": [w["window_index"] for w in result["per_window"]],
        "concept_f1": result["micro"]["concept"]["f1"],
        "inputs_sha256": {lab: sha for lab, (_, sha) in docs.items()},
    }


def score_report(lecture_id: str, arms: list[Any], root: Path | None) -> dict[str, Any]:
    from matching import load_adjudications
    from scoring import adjudications_summary, load_gold, micro_string_f1_on, score_arm

    gpath, apath = gold_path(lecture_id, root), adjudications_path(lecture_id, root)
    gold = load_gold(gpath, lecture_id)
    adj = load_adjudications(apath, lecture_id) if apath.is_file() else {}
    scores = [score_arm(arm, gold, adj) for arm in arms]
    cons = consistency(lecture_id, root)
    shared = set(cons.get("windows", []))
    headline = {  # ADR-0048 section 6: the consistency figure sits only next to string-rule-only model F1
        "note": "string rule only on both sides; the adjudicated F1 is never compared with this figure. Gold is "
                "single-annotator (ADR-0048 Amendment 1).",
        "consistency": cons,
        "model_string_rule_concept_f1": {s["name"]: s["string_rule"]["micro"]["concept"]["f1"] for s in scores},
        "model_string_rule_concept_f1_on_consistency_windows": (
            {s["name"]: micro_string_f1_on(s, shared) for s in scores} if shared else None),
    }
    return {
        "lecture_id": lecture_id,
        "gold": {"path": str(gpath), "sha256": sha256_file(gpath), "windows": len(gold["windows"])},
        "adjudications": adjudications_summary(apath),
        "headline_string_rule": headline,
        "arms": scores,
    }


def print_score(s: dict[str, Any]) -> None:
    v = s["validity"]
    state = "VALID" if v["valid"] else f"INVALID (invalid {v['invalid_windows']}, missing {v['missing_windows']})"
    print(f"arm {s['name']}: {state}; retried windows {len(v['retried_windows'])}; "
          f"dropped relations {s['dropped_relations']}")
    for part, title in (("adjudicated", "adjudicated (primary)"), ("string_rule", "string rule only")):
        c = s[part]["micro"]["concept"]
        print(f"  concept {title}: tp {c['tp']} pred {c['pred']} gold {c['ref']}; P {fmt_ratio(c['precision'])} "
              f"R {fmt_ratio(c['recall'])} F1 {c['f1']:.3f}")
    print(f"  pending adjudication: {s['adjudicated']['pending']}")
    r, imp = s["adjudicated"]["micro"]["relation"], s["adjudicated"]["micro"]["important"]
    print(f"  relation (adjudicated mapping): P {fmt_ratio(r['precision'])} R {fmt_ratio(r['recall'])} F1 "
          f"{r['f1']:.3f}; important: P {fmt_ratio(imp['precision'])} R {fmt_ratio(imp['recall'])}")


def default_report_path(arms: list[Any], name: str) -> Path:
    return arms[0].directory.parent / name


def cmd_score(a: argparse.Namespace) -> int:
    arms = load_arms(a.arm)
    report = score_report(a.lecture, arms, a.labels_root)
    for s in report["arms"]:
        print_score(s)
    h = report["headline_string_rule"]
    cons = h["consistency"]
    print("string rule only, next to the consistency figure:")
    for name, f in h["model_string_rule_concept_f1"].items():
        print(f"  {name}: model concept F1 {f:.3f}")
    print(f"  consistency (single annotator): {cons['concept_f1']:.3f} on {len(cons['windows'])} windows"
          if cons["available"] else f"  consistency: not available ({cons['reason']})")
    out = Path(a.out) if a.out else default_report_path(arms, "score.json")
    write_json(out, report)
    print(f"wrote {out}")
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    from scoring import compare

    arms = load_arms([a.a, a.b])
    report = score_report(a.lecture, arms, a.labels_root)
    result = compare(a.comparison, report["arms"][0], report["arms"][1])
    for s in report["arms"]:
        print_score(s)
    print(f"{a.comparison}: A = {result['arm_a']}, B = {result['arm_b']}; wins A {result['wins_a']}, B "
          f"{result['wins_b']}, ties {result['ties']}; net for B {result['net_wins_b']}; micro F1 A "
          f"{result['micro_concept_f1_a']:.3f}, B {result['micro_concept_f1_b']:.3f}")
    print(f"decision: {result['decision']} ({result['reason']})")
    out = Path(a.out) if a.out else default_report_path(arms, f"compare_{a.comparison}.json")
    write_json(out, {**report, "comparison": result})
    print(f"wrote {out}")
    return 0


def cmd_adjudication_sheet(a: argparse.Namespace) -> int:
    from adjudication import build_sheet
    from matching import load_adjudications
    from scoring import load_gold

    arms = load_arms(a.arm)
    gpath, apath = gold_path(a.lecture, a.labels_root), adjudications_path(a.lecture, a.labels_root)
    gold = load_gold(gpath, a.lecture)
    adj = load_adjudications(apath, a.lecture) if apath.is_file() else {}
    sheet = build_sheet(a.lecture, a.comparison, gold, sha256_file(gpath), arms, adj, a.seed)
    stamp = sheet["created_at"].replace("-", "").replace(":", "")
    out = lecture_dir(a.lecture, a.labels_root) / "adjudication_sheets" / f"{a.comparison}-{stamp}.json"
    if out.exists():
        raise SystemExit(f"{out} exists")
    write_json(out, sheet)
    print(f"wrote {out}: {len(sheet['entries'])} entries to decide (seed {sheet['seed']}); "
          f"{len(adj)} earlier decisions reused")
    print(f"decide them with: label_concepts.py adjudicate --lecture {a.lecture} --sheet {out}")
    return 0


def cmd_adjudicate(a: argparse.Namespace) -> int:
    from adjudication import check_sheet, load_sheet, record_decisions

    sheet, ssha = load_sheet(Path(a.sheet))
    gpath = gold_path(a.lecture, a.labels_root)
    check_sheet(sheet, a.lecture, sha256_file(gpath))
    counts = record_decisions(sheet, ssha, adjudications_path(a.lecture, a.labels_root), a.by)
    print(f"\nrecorded {counts['match']} match, {counts['no_match']} no-match; skipped {counts['skipped']}; "
          f"{counts['remaining']} still undecided")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", help="Insightex data directory (default $INSIGHTEX_DATA or ~/insightex-data)")
    p.add_argument("--labels-root", type=Path, default=None, help=argparse.SUPPRESS)  # tests
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="draw the seeded stratified window sample and write sample.json")
    s.add_argument("--lecture", required=True, help="workspace id, e.g. sha256-... or yt-...")
    s.add_argument("--n", type=int, default=40, help="windows to sample; >= eligible windows gives the census")
    s.add_argument("--shared", type=int, default=10, help="windows labelled by every labeller (agreement)")
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--labellers", nargs="+", default=list(DEFAULT_LABELLERS),
                   help="one name: single labeller, the shared windows are for the repeat; two or more: shared "
                   "windows are labelled by all, the rest alternate")
    s.add_argument("--exclude", action="append", default=[], metavar="I=REASON",
                   help="leave window I out of the sample (recorded with REASON); repeatable")
    s.add_argument("--allow-untested", action="store_true", help="sample a lecture with an untested language")
    s.add_argument("--force", action="store_true", help="overwrite an existing sample.json")
    s.set_defaults(fn=cmd_sample)
    s = sub.add_parser("reassign", help="change who labels which window (same windows and seed; recorded in "
                       "sample.json under amendments)")
    s.add_argument("--lecture", required=True)
    s.add_argument("--labellers", nargs="+", required=True)
    s.add_argument("--note", required=True, help="why, e.g. the ADR amendment")
    s.set_defaults(fn=cmd_reassign)
    s = sub.add_parser("serve", help="label in the browser at http://127.0.0.1:<port>/")
    s.add_argument("--lecture", required=True)
    s.add_argument("--labeller", required=True, help="a name from the manifest, <name>_repeat for the blind "
                   "repeat of the shared windows, or 'consensus'")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("validate", help="check a labels file against the schema and the sample manifest")
    s.add_argument("--lecture", required=True)
    s.add_argument("--labeller", required=True)
    s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("agreement", help="agreement on the shared windows (two labellers, or a labeller and their "
                       "_repeat)")
    s.add_argument("--lecture", required=True)
    s.add_argument("--a", required=True, help="reference labeller")
    s.add_argument("--b", required=True)
    s.add_argument("--adjudications", help="adjudication file (ADR-0048); default: string rule only")
    s.set_defaults(fn=cmd_agreement)
    s = sub.add_parser("merge", help="write gold.json (one labeller: their file alone; else consensus + own windows)")
    s.add_argument("--lecture", required=True)
    s.set_defaults(fn=cmd_merge)
    s = sub.add_parser("adjudication-sheet", help="blind sheet of the model concepts the string rule left unmatched, "
                       "pooled over the arms of one comparison")
    s.add_argument("--lecture", required=True)
    s.add_argument("--comparison", required=True, help="C1, C2, C3 or C4")
    s.add_argument("--arm", action="append", required=True, metavar="NAME=RUN_DIR", help="repeat for every arm")
    s.add_argument("--seed", type=int, help="shuffle seed (default: random; always recorded in the sheet)")
    s.set_defaults(fn=cmd_adjudication_sheet)
    s = sub.add_parser("adjudicate", help="decide the sheet's entries in the terminal (appended to adjudications.json)")
    s.add_argument("--lecture", required=True)
    s.add_argument("--sheet", required=True)
    s.add_argument("--by", default=DEFAULT_LABELLERS[0], help="who decides (recorded per entry)")
    s.set_defaults(fn=cmd_adjudicate)
    s = sub.add_parser("score", help="score model runs against gold.json (validity, P/R/F1, consistency figure)")
    s.add_argument("--lecture", required=True)
    s.add_argument("--arm", action="append", required=True, metavar="NAME=RUN_DIR")
    s.add_argument("--out", help="report file (default: score.json next to the first run directory)")
    s.set_defaults(fn=cmd_score)
    s = sub.add_parser("compare", help="ADR-0048 section 7 decision between arm A (kept on a tie) and arm B")
    s.add_argument("--lecture", required=True)
    s.add_argument("--comparison", required=True, choices=["C1", "C2", "C3", "C4"])
    s.add_argument("--a", required=True, metavar="NAME=RUN_DIR", help="arm A, kept on a tie")
    s.add_argument("--b", required=True, metavar="NAME=RUN_DIR")
    s.add_argument("--out", help="report file (default: compare_<comparison>.json next to arm A's run directory)")
    s.set_defaults(fn=cmd_compare)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
