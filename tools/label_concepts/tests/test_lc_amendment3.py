"""ADR-0048 Amendment 3 on a synthetic lecture: a shared-windows-only second annotator, agreement on the gold
labeller's pre-review labels, logged corrections enforced by validate, and merge from the gold labeller alone."""

import json

import label_concepts as lc
import pytest
from grid import build_grid
from lc_fixtures import concept, make_workspace, record, toy_segments
from server import LabelStore

LECTURE = "sha256-" + "3" * 32


@pytest.fixture
def env(tmp_path):
    segs = toy_segments(8)
    grid = build_grid(segs, 240)
    index = [{"id": w.index, "start": w.start_s, "end": w.end_s, "text": w.text} for w in grid]
    make_workspace(tmp_path / "data", LECTURE, segs, 240, index_windows=index)
    root = tmp_path / "labels"

    def run(*args):
        return lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(root), *args])

    assert run("sample", "--lecture", LECTURE, "--n", "8", "--shared", "4") == 0
    return run, root


def label(root, name, recs_for):
    m, msha = lc.load_manifest(LECTURE, root)
    rows = lc.windows_for(m, name)
    store = LabelStore(root / LECTURE / f"{name}.json", LECTURE, name, msha, rows,
                       frozenset(lc.accepted_manifest_sha256(m, msha)))
    for r in rows:
        store.save(record(LECTURE, r["window_index"], r["start_s"], r["end_s"], concepts=recs_for(r)))
    return m, store


def test_add_annotator_records_amendment_and_scopes_fatima_to_shared_windows(env, capsys):
    run, root = env
    _, old_sha = lc.load_manifest(LECTURE, root)
    label(root, "bilal", lambda r: [concept(f"t{r['window_index']}")])
    assert run("add-annotator", "--lecture", LECTURE, "--labeller", "fatima", "--note", "Amendment 3") == 0
    m, _ = lc.load_manifest(LECTURE, root)
    shared = [r["window_index"] for r in m["windows"] if r["shared"]]
    assert m["labellers"] == ["bilal"] and m["shared_annotators"] == ["fatima"]
    assert m["amendments"][-1]["previous_sha256"] == old_sha and m["amendments"][-1]["windows"] == shared
    assert [r["window_index"] for r in lc.windows_for(m, "fatima")] == shared
    assert len(lc.windows_for(m, "bilal")) == 8  # the gold labeller's windows are unchanged
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0  # made against the old manifest
    with pytest.raises(SystemExit):
        run("add-annotator", "--lecture", LECTURE, "--labeller", "fatima", "--note", "again")
    with pytest.raises(SystemExit, match="drop"):
        run("reassign", "--lecture", LECTURE, "--labellers", "bilal", "--note", "x")
    label(root, "fatima", lambda r: [concept(f"t{r['window_index']}")])
    capsys.readouterr()
    assert run("validate", "--lecture", LECTURE, "--labeller", "fatima") == 0
    assert f"valid, {len(shared)} windows" in capsys.readouterr().out
    doc = json.loads((root / LECTURE / "fatima.json").read_text())
    other = next(r for r in m["windows"] if not r["shared"])
    doc["windows"].append(record(LECTURE, other["window_index"], other["start_s"], other["end_s"]))
    (root / LECTURE / "fatima.json").write_text(json.dumps(doc))
    assert run("validate", "--lecture", LECTURE, "--labeller", "fatima") == 1  # only the shared windows


def test_agreement_on_pre_review_labels_corrections_logged_and_merge(env, capsys):
    run, root = env
    label(root, "bilal", lambda r: [concept(f"t{r['window_index']}")])
    assert run("add-annotator", "--lecture", LECTURE, "--labeller", "fatima", "--note", "Amendment 3") == 0
    m, _ = lc.load_manifest(LECTURE, root)
    shared = [r for r in m["windows"] if r["shared"]]
    first = shared[0]["window_index"]
    label(root, "fatima", lambda r: [concept("other" if r["window_index"] == first else f"t{r['window_index']}")])
    assert run("agreement", "--lecture", LECTURE, "--a", "bilal", "--b", "fatima") == 0
    pre = root / LECTURE / "bilal_pre_review.json"
    assert pre.is_file()
    report = json.loads((root / LECTURE / "agreement_bilal_fatima.json").read_text())
    assert report["micro"]["concept"]["f1"] == pytest.approx(6 / 8)
    assert report["inputs"]["bilal"]["path"].endswith("bilal_pre_review.json")

    # Bilal corrects window `first` in serve; validate refuses until the correction is logged
    _, store = label(root, "bilal", lambda r: [concept("other" if r["window_index"] == first else f"t{r['window_index']}")])
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1
    with pytest.raises(SystemExit):
        run("merge", "--lecture", LECTURE)
    with pytest.raises(SystemExit, match="not a shared window"):
        run("log-correction", "--lecture", LECTURE, "--window", str(next(r for r in m["windows"]
                                                                         if not r["shared"])["window_index"]),
            "--reason", "x")
    assert run("log-correction", "--lecture", LECTURE, "--window", str(first), "--reason", "clear error: wrong "
               "concept") == 0
    with pytest.raises(SystemExit, match="has not changed"):
        run("log-correction", "--lecture", LECTURE, "--window", str(first), "--reason", "again")
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0
    log = json.loads((root / LECTURE / "corrections_bilal.json").read_text())
    assert log["entries"][0]["before"]["concepts"][0]["label"] == f"t{first}"
    assert log["entries"][0]["after"]["concepts"][0]["label"] == "other"

    # a change to a non-shared window after the review started is refused even if it would be logged
    other = next(r for r in m["windows"] if not r["shared"])
    store.save(record(LECTURE, other["window_index"], other["start_s"], other["end_s"], concepts=[concept("new")]))
    capsys.readouterr()
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1
    assert "only shared windows may be corrected" in capsys.readouterr().out
    store.save(record(LECTURE, other["window_index"], other["start_s"], other["end_s"],
                      concepts=[concept(f"t{other['window_index']}")]))

    # agreement re-run still uses the pre-review labels, so corrections cannot raise the figure
    assert run("agreement", "--lecture", LECTURE, "--a", "bilal", "--b", "fatima") == 0
    report = json.loads((root / LECTURE / "agreement_bilal_fatima.json").read_text())
    assert report["micro"]["concept"]["f1"] == pytest.approx(6 / 8)
    assert lc.annotator_agreement(LECTURE, root)["concept_f1"] == pytest.approx(6 / 8)

    assert run("merge", "--lecture", LECTURE) == 0
    gold = json.loads((root / LECTURE / "gold.json").read_text())
    assert len(gold["windows"]) == 8 and gold["producer"]["name"] == "gold: bilal (single annotator)"
    assert {r["window"]["window_index"]: r["concepts"][0]["label"] for r in gold["windows"]}[first] == "other"
