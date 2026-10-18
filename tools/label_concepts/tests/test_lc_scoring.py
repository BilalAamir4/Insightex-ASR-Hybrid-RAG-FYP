"""Scorer, comparison rule, blind adjudication sheet and the append-only adjudications file (ADR-0048), on synthetic
gold and synthetic arm runs."""

import json

import label_concepts as lc
import pytest
from adjudication import append_adjudication, build_sheet, record_decisions
from lc_fixtures import concept, gold_doc, make_workspace, record, rel, toy_segments, write_run
from matching import load_adjudications
from scoring import compare, load_arm_run, score_arm
from server import LabelStore

LECTURE = "sha256-" + "1" * 32


def rec(i, **kw):
    return record(LECTURE, i, 30.0 * i, 30.0 * i + 30, **kw)


def cs(*labels):
    return [concept(x) for x in labels]


def arm(tmp_path, name, records, **kw):
    return load_arm_run(name, write_run(tmp_path / name, LECTURE, name, records, **kw))


# -- scoring -------------------------------------------------------------------------------------------------------


def test_string_rule_adjudication_pending_and_dropped(tmp_path):
    gold = gold_doc(LECTURE, [
        rec(0, concepts=[concept("batch learning", "offline learning"), concept("online learning")],
            relations=[rel("batch learning", "contrasts_with", "online learning")], important=True, cue="exam"),
        rec(1, concepts=cs("learning rate")),
        rec(2),  # no concepts in gold
    ])
    a = arm(tmp_path, "A", [
        rec(0, concepts=[concept("Offline-Learning"), concept("incremental learning")],
            relations=[rel("incremental learning", "contrasts_with", "Offline-Learning")], important=True, cue="x"),
        rec(1, concepts=cs("step size")),
        rec(2),
    ], dropped={0: 2, 1: 1}, retried=(1,))
    adj = {(0, "incrementallearning"): "online learning"}  # window 1 "step size" has no decision: pending
    s = score_arm(a, gold, adj)
    assert s["validity"]["valid"] and s["validity"]["retried_windows"] == [1]
    assert s["dropped_relations"] == 3
    st = s["string_rule"]["micro"]
    assert (st["concept"]["tp"], st["concept"]["pred"], st["concept"]["ref"]) == (1, 3, 3)
    ad = s["adjudicated"]["micro"]
    assert (ad["concept"]["tp"], ad["concept"]["pred"], ad["concept"]["ref"]) == (2, 3, 3)
    assert s["adjudicated"]["pending"] == 1
    assert s["adjudicated"]["pending_concepts"] == [{"window_index": 1, "model_label": "step size"}]
    # the relation maps through the adjudicated pair (contrasts_with is symmetric) but not under the string rule
    assert ad["relation"]["tp"] == 1 and st["relation"]["tp"] == 0
    assert ad["important"]["precision"] == 1.0 and ad["important"]["recall"] == 1.0
    pw = {r["window_index"]: r for r in s["adjudicated"]["per_window"]}
    assert pw[2]["concept_f1"] == 1.0  # both empty
    assert pw[1]["concept_f1"] == 0.0


def test_adjudication_used_only_if_gold_concept_still_unmatched(tmp_path):
    gold = gold_doc(LECTURE, [rec(0, concepts=cs("gradient descent"))])
    a = arm(tmp_path, "A", [rec(0, concepts=cs("gradient descent", "GD algorithm"))])
    s = score_arm(a, gold, {(0, "gdalgorithm"): "gradient descent"})
    c = s["adjudicated"]["micro"]["concept"]
    assert (c["tp"], c["pred"]) == (1, 2) and s["adjudicated"]["pending"] == 0


def test_validity_missing_invalid_and_schema_errors(tmp_path):
    gold = gold_doc(LECTURE, [rec(0, concepts=cs("x")), rec(1, concepts=cs("y")), rec(2)])
    s = score_arm(arm(tmp_path, "A", [rec(0, concepts=cs("x")), rec(1, concepts=cs("y"))]), gold, {})
    assert not s["validity"]["valid"] and s["validity"]["missing_windows"] == [2]
    s = score_arm(arm(tmp_path, "B", [rec(0, concepts=cs("x")), rec(1), rec(2)], invalid=(1,)), gold, {})
    assert not s["validity"]["valid"] and s["validity"]["invalid_windows"] == [1]
    bad = rec(0, concepts=cs("x"), relations=[rel("x", "part_of", "nowhere")])  # dangling left in: schema error
    s = score_arm(arm(tmp_path, "C", [bad, rec(1), rec(2)]), gold, {})
    assert not s["validity"]["valid"] and s["validity"]["schema_errors"]


def test_valid_but_empty_after_retry_is_reported_apart(tmp_path, capsys):
    """ADR-0049 Amendment 2: a window valid only through the retry whose record is empty is its own category."""
    gold = gold_doc(LECTURE, [rec(0, concepts=cs("x")), rec(1, concepts=cs("y")), rec(2, concepts=cs("z"))])
    run = arm(tmp_path, "A", [rec(0, concepts=cs("x")), rec(1), rec(2, concepts=cs("z"))], retried=(1, 2))
    s = score_arm(run, gold, {})
    v = s["validity"]
    assert v["valid"] and v["retried_windows"] == [1, 2] and v["valid_empty_after_retry_windows"] == [1]
    lc.print_score(s)
    assert "valid but empty after retry 1 [1]" in capsys.readouterr().out
    plain = score_arm(arm(tmp_path, "B", [rec(0, concepts=cs("x")), rec(1), rec(2)]), gold, {})
    assert plain["validity"]["valid_empty_after_retry_windows"] == []  # empty on the first attempt: ordinary


# -- comparison ----------------------------------------------------------------------------------------------------


def two_of(i):
    return [f"c{i}a", f"c{i}b"]


def setup_compare(tmp_path, n_small, big=False):
    """Windows 0..n_small-1: gold has 2 concepts, A finds 1 (F1 2/3), B finds 2 (F1 1). Optional big window: gold 10
    concepts, A finds all, B none. No false positives anywhere, so nothing is pending."""
    gold_recs, a_recs, b_recs = [], [], []
    for i in range(n_small):
        gold_recs.append(rec(i, concepts=cs(*two_of(i))))
        a_recs.append(rec(i, concepts=cs(two_of(i)[0])))
        b_recs.append(rec(i, concepts=cs(*two_of(i))))
    if big:
        i = n_small
        labels = [f"big{k}" for k in range(10)]
        gold_recs.append(rec(i, concepts=cs(*labels)))
        a_recs.append(rec(i, concepts=cs(*labels)))
        b_recs.append(rec(i))
    gold = gold_doc(LECTURE, gold_recs)
    return gold, score_arm(arm(tmp_path, "A", a_recs), gold, {}), score_arm(arm(tmp_path, "B", b_recs), gold, {})


def test_net_two_is_a_tie_and_keeps_a(tmp_path):
    _, a, b = setup_compare(tmp_path, 2)
    r = compare("C3", a, b)
    assert (r["wins_b"], r["net_wins_b"], r["decision"]) == (2, 2, "keep_a")
    assert r["tie_keeps_arm_a_because"] == "single-window calls"


def test_net_three_with_higher_f1_adopts_b(tmp_path):
    _, a, b = setup_compare(tmp_path, 3)
    r = compare("C2", a, b)
    assert (r["net_wins_b"], r["decision"]) == (3, "adopt_b")


def test_net_three_but_lower_micro_f1_keeps_a(tmp_path):
    _, a, b = setup_compare(tmp_path, 4, big=True)
    r = compare("C1", a, b)
    assert r["net_wins_b"] == 3 and r["micro_concept_f1_b"] < r["micro_concept_f1_a"]
    assert r["decision"] == "keep_a" and "lower" in r["reason"]


def test_validity_rule_decides_before_scores(tmp_path):
    gold, a, b = setup_compare(tmp_path, 3)
    bad_b = score_arm(arm(tmp_path, "Bx", [rec(i, concepts=cs(*two_of(i))) for i in range(3)], invalid=(0,)), gold, {})
    assert compare("C2", a, bad_b)["decision"] == "keep_a"
    bad_a = score_arm(arm(tmp_path, "Ax", [rec(i, concepts=cs(two_of(i)[0])) for i in range(3)], invalid=(2,)), gold, {})
    assert compare("C2", bad_a, b)["decision"] == "adopt_b"
    r = compare("C2", bad_a, bad_b)
    assert r["decision"] == "no_decision" and "never pick" in r["reason"]


def test_compare_refuses_with_pending_adjudications(tmp_path):
    gold = gold_doc(LECTURE, [rec(0, concepts=cs("x"))])
    a = score_arm(arm(tmp_path, "A", [rec(0, concepts=cs("x"))]), gold, {})
    b = score_arm(arm(tmp_path, "B", [rec(0, concepts=cs("x", "unseen"))]), gold, {})
    with pytest.raises(SystemExit, match="adjudication"):
        compare("C1", a, b)


# -- adjudication sheet ----------------------------------------------------------------------------------------------


def sheet_inputs(tmp_path):
    gold = gold_doc(LECTURE, [rec(0, concepts=[concept("online learning", "incremental learning")]),
                              rec(1, concepts=cs("learning rate", "epoch"))])
    a = arm(tmp_path, "armA", [rec(0, concepts=[concept("streaming learning", "live learning")]),
                               rec(1, concepts=cs("step size", "decided before"))])
    b = arm(tmp_path, "armB", [rec(0, concepts=[concept("Streaming-Learning", "stream learning")]),
                               rec(1, concepts=cs("learning rate", "mini batch"))])
    return gold, [a, b]


def test_sheet_pools_dedupes_skips_decided_and_hides_arms(tmp_path):
    gold, arms = sheet_inputs(tmp_path)
    sheet = build_sheet(LECTURE, "C1", gold, "g" * 64, arms, {(1, "decidedbefore"): None}, seed=11)
    keys = sorted((e["window_index"], e["model_label"]) for e in sheet["entries"])
    assert keys == [(0, "Streaming-Learning"), (1, "mini batch"), (1, "step size")]
    streaming = next(e for e in sheet["entries"] if e["window_index"] == 0)
    assert streaming["model_aliases"] == ["live learning", "stream learning"]  # union over arms
    assert streaming["gold_concepts"] == [{"label": "online learning", "aliases": ["incremental learning"]}]
    assert [e["entry"] for e in sheet["entries"]] == [1, 2, 3] and sheet["seed"] == 11
    text = json.dumps(sheet)
    assert "armA" not in text and "armB" not in text
    again = build_sheet(LECTURE, "C1", gold, "g" * 64, list(reversed(arms)), {(1, "decidedbefore"): None}, seed=11)
    assert again["entries"] == sheet["entries"]  # the seed alone fixes the order, not the arm order
    orders = {tuple(e["model_label"] for e in build_sheet(LECTURE, "C1", gold, "g" * 64, arms, {}, seed=s)["entries"])
              for s in range(20)}
    assert len(orders) > 1  # the shuffle depends on the seed


def test_record_decisions_appends_and_never_changes_entries(tmp_path):
    gold, arms = sheet_inputs(tmp_path)
    sheet = build_sheet(LECTURE, "C1", gold, "g" * 64, arms, {}, seed=3)
    by_label = {e["model_label"]: e for e in sheet["entries"]}
    answers = []
    for e in sheet["entries"]:
        if e["model_label"] == "Streaming-Learning":
            answers += ["9", "1"]  # 9 is out of range and is asked again
        elif e["model_label"] == "step size":
            answers += ["1"]  # learning rate
        elif e["model_label"] == "mini batch":
            answers += ["s"]
        else:
            answers += ["n"]
    it = iter(answers)
    path = tmp_path / "adjudications.json"
    counts = record_decisions(sheet, "s" * 64, path, "bilal", ask=lambda _: next(it), say=lambda _: None)
    assert counts["match"] == 2 and counts["skipped"] == 1
    adj = load_adjudications(path, LECTURE)
    assert adj[(0, "streaminglearning")] == "online learning" and adj[(1, "stepsize")] == "learning rate"
    assert (1, "minibatch") not in adj
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="append-only"):
        append_adjudication(path, LECTURE, {"window_index": 1, "model_label": "Step Size", "gold_label": None,
                                            "decided_by": "bilal", "decided_at": "t"})
    assert path.read_text(encoding="utf-8") == before
    # a second pass only asks about what is still undecided; q stops without recording
    asked = []
    record_decisions(sheet, "s" * 64, path, "bilal", ask=lambda p: asked.append(p) or "q", say=lambda _: None)
    assert len(asked) == 1 and by_label["mini batch"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["entries"][0]["sheet_sha256"] == "s" * 64 and doc["entries"][0]["decided_by"] == "bilal"


# -- CLI: full flow with the inter-annotator figure -------------------------------------------------------------------


def test_cli_flow_sheet_adjudicate_score_compare(tmp_path, monkeypatch, capsys):
    from grid import build_grid

    segs = toy_segments(6)
    grid = build_grid(segs, 180)
    index = [{"id": w.index, "start": w.start_s, "end": w.end_s, "text": w.text} for w in grid]
    make_workspace(tmp_path / "data", LECTURE, segs, 180, index_windows=index)
    root = tmp_path / "labels"

    def run(*args):
        return lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(root), *args])

    assert run("sample", "--lecture", LECTURE, "--n", "6", "--shared", "3") == 0
    m, msha = lc.load_manifest(LECTURE, root)
    rows = m["windows"]
    labels = {r["window_index"]: cs(f"topic {r['window_index']}") for r in rows}

    def gold_rec(r, concepts):
        return record(LECTURE, r["window_index"], r["start_s"], r["end_s"], concepts=concepts)

    store = LabelStore(root / LECTURE / "bilal.json", LECTURE, "bilal", msha, lc.windows_for(m, "bilal"))
    for r in rows:
        store.save(gold_rec(r, labels[r["window_index"]]))
    assert run("add-annotator", "--lecture", LECTURE, "--labeller", "fatima", "--note", "test") == 0
    m, msha = lc.load_manifest(LECTURE, root)
    rep = lc.windows_for(m, "fatima")
    store = LabelStore(root / LECTURE / "fatima.json", LECTURE, "fatima", msha, rep, frozenset(
        lc.accepted_manifest_sha256(m, msha)))
    for k, r in enumerate(rep):  # the second annotator agrees on all but one shared window
        store.save(gold_rec(r, labels[r["window_index"]] if k else cs("something else")))
    assert run("merge", "--lecture", LECTURE) == 0

    def model_recs(extra):
        return [gold_rec(r, labels[r["window_index"]] + (cs(extra) if r["order"] == 0 else [])) for r in rows]

    da = write_run(tmp_path / "runs" / "A", LECTURE, "A", model_recs("near miss"))
    db = write_run(tmp_path / "runs" / "B", LECTURE, "B", model_recs("near miss"))
    spec_a, spec_b = f"A={da}", f"B={db}"
    with pytest.raises(SystemExit, match="adjudication"):
        run("compare", "--lecture", LECTURE, "--comparison", "C1", "--a", spec_a, "--b", spec_b)
    assert run("adjudication-sheet", "--lecture", LECTURE, "--comparison", "C1", "--arm", spec_a, "--arm", spec_b,
               "--seed", "5") == 0
    sheets = list((root / LECTURE / "adjudication_sheets").glob("C1-*.json"))
    assert len(sheets) == 1 and len(json.loads(sheets[0].read_text())["entries"]) == 1  # deduped across arms
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert run("adjudicate", "--lecture", LECTURE, "--sheet", str(sheets[0])) == 0
    capsys.readouterr()
    assert run("compare", "--lecture", LECTURE, "--comparison", "C1", "--a", spec_a, "--b", spec_b) == 0
    out = capsys.readouterr().out
    assert "decision: keep_a" in out and "near miss" not in out
    report = json.loads((tmp_path / "runs" / "compare_C1.json").read_text())
    cons = report["headline_string_rule"]["inter_annotator_agreement"]
    assert cons["available"] and len(cons["windows"]) == 3 and cons["concept_f1"] == pytest.approx(4 / 6)
    assert "bilal pre-review vs fatima" in cons["kind"]
    assert report["adjudications"]["entries"] == 1 and report["comparison"]["net_wins_b"] == 0
    # the adjudicated F1 stays out of the headline next to the inter-annotator figure
    assert set(report["headline_string_rule"]) == {"note", "inter_annotator_agreement", "model_string_rule_concept_f1",
                                                   "model_string_rule_concept_f1_on_agreement_windows"}
    assert run("score", "--lecture", LECTURE, "--arm", spec_a) == 0
    assert json.loads((tmp_path / "runs" / "score.json").read_text())["arms"][0]["adjudicated"]["pending"] == 0
