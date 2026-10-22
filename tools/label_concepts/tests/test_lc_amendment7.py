"""ADR-0048 Amendment 7 on a synthetic lecture: gold v2.1 = frozen gold v2 plus one logged concept, and its
adjudications started from v2's frozen decisions minus the window to decide again."""

import json

import label_concepts as lc
import pytest
from adjudication import append_adjudication
from lc_fixtures import concept, record, write_run
from test_lc_amendment5 import LECTURE, env, review_all  # noqa: F401 - env is a pytest fixture


@pytest.fixture
def v2(env):  # noqa: F811
    run, root, tmp = env
    run("relabel-start", "--lecture", LECTURE)
    review_all(root)
    assert run("relabel-merge", "--lecture", LECTURE) == 0
    gold = json.loads((root / LECTURE / "gold_v2.json").read_text())
    return run, root, tmp, gold


def add(run, window, label="hardware limitation", reason="explained here"):
    return run("gold-add", "--lecture", LECTURE, "--from", "v2", "--to", "v2.1", "--window", str(window),
               "--label", label, "--reason", reason, "--amendment", "7")


def test_gold_add_writes_v2_1_and_its_log_leaving_v2_unchanged(v2):
    run, root, _, gold = v2
    d = root / LECTURE
    before = (d / "gold_v2.json").read_bytes()
    i = gold["windows"][0]["window"]["window_index"]
    assert add(run, i) == 0
    assert (d / "gold_v2.json").read_bytes() == before
    v21 = json.loads((d / "gold_v2_1.json").read_text())
    assert v21["windows"][0]["concepts"] == [*gold["windows"][0]["concepts"], concept("hardware limitation")]
    assert v21["windows"][1:] == gold["windows"][1:] and "Amendment 7" in v21["producer"]["name"]
    log = json.loads((d / "gold_v2_1_changes.json").read_text())
    assert log["base"] == {"file": "gold_v2.json", "sha256": lc.sha256_file(d / "gold_v2.json")}
    assert log["entries"][0]["reason"] == "explained here" and log["gold_sha256"] == lc.sha256_file(d / "gold_v2_1.json")
    with pytest.raises(SystemExit, match="written once"):
        add(run, i)


def test_gold_add_refuses_an_invalid_concept_and_no_reason(v2):
    run, root, _, gold = v2
    i = gold["windows"][0]["window"]["window_index"]
    with pytest.raises(SystemExit, match="also a name of concept"):
        add(run, i, label=gold["windows"][0]["concepts"][0]["label"])
    with pytest.raises(SystemExit, match="needs a reason"):
        add(run, i, reason=" ")
    with pytest.raises(SystemExit, match="not a gold window"):
        add(run, 999)
    assert not (root / LECTURE / "gold_v2_1.json").exists()


def test_carry_leaves_out_the_window_and_the_v2_1_sheet_lists_only_it(v2, tmp_path):
    run, root, _, gold = v2
    d = root / LECTURE
    idx = [r["window"]["window_index"] for r in gold["windows"]]
    arm = write_run(tmp_path / "arm", LECTURE, "a", [
        record(LECTURE, r["window"]["window_index"], r["window"]["start_s"], r["window"]["end_s"],
               concepts=[concept("limits of hardware")]) for r in gold["windows"]])
    for i in idx:  # frozen v2 decisions: every unmatched concept decided "no match"
        append_adjudication(d / "adjudications_v2.json", LECTURE, {
            "window_index": i, "model_label": "limits of hardware", "gold_label": None, "decided_by": "bilal",
            "decided_at": "t", "sheet_sha256": "s"})
    v2_adj = (d / "adjudications_v2.json").read_bytes()
    add(run, idx[0])
    assert run("adjudications-carry", "--lecture", LECTURE, "--from", "v2", "--to", "v2.1",
               "--redecide-window", str(idx[0])) == 0
    carried = json.loads((d / "adjudications_v2_1.json").read_text())["entries"]
    assert sorted(e["window_index"] for e in carried) == sorted(idx[1:])
    assert all(e["carried_from"]["file"] == "adjudications_v2.json" for e in carried)
    assert (d / "adjudications_v2.json").read_bytes() == v2_adj
    with pytest.raises(SystemExit, match="exists"):
        run("adjudications-carry", "--lecture", LECTURE, "--from", "v2", "--to", "v2.1")
    assert run("adjudication-sheet", "--lecture", LECTURE, "--gold", "v2.1", "--comparison", "C1",
               "--arm", f"a={arm}", "--seed", "3") == 0
    sheet = json.loads(next((d / "adjudication_sheets").glob("C1-gold_v2_1-*.json")).read_text())
    assert [e["window_index"] for e in sheet["entries"]] == [idx[0]]
    assert sheet["entries"][0]["gold_concepts"][-1]["label"] == "hardware limitation"
