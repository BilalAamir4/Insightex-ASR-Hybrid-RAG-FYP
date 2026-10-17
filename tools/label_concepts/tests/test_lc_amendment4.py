"""ADR-0048 Amendment 4 on a synthetic lecture: on a non-shared gold window, a logged correction may only delete or
reverse relations; shared-window corrections work as under Amendment 3."""

import json

import label_concepts as lc
import pytest
from grid import build_grid
from lc_fixtures import concept, make_workspace, record, rel, toy_segments
from server import LabelStore

LECTURE = "sha256-" + "4" * 32


def labels_for(r):
    i = r["window_index"]
    return {"concepts": [concept(f"a{i}"), concept(f"b{i}")], "relations": [rel(f"a{i}", "part_of", f"b{i}"),
                                                                           rel(f"b{i}", "contrasts_with", f"a{i}")]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    segs = toy_segments(8)
    grid = build_grid(segs, 240)
    index = [{"id": w.index, "start": w.start_s, "end": w.end_s, "text": w.text} for w in grid]
    make_workspace(tmp_path / "data", LECTURE, segs, 240, index_windows=index)
    root = tmp_path / "labels"
    monkeypatch.setattr(lc, "AMENDMENT4_LECTURES", frozenset({LECTURE}))

    def run(*args):
        return lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(root), *args])

    assert run("sample", "--lecture", LECTURE, "--n", "8", "--shared", "4") == 0
    store = save_all(root, "bilal", labels_for)
    assert run("add-annotator", "--lecture", LECTURE, "--labeller", "fatima", "--note", "Amendment 3") == 0
    save_all(root, "fatima", labels_for)
    assert run("agreement", "--lecture", LECTURE, "--a", "bilal", "--b", "fatima") == 0
    m, _ = lc.load_manifest(LECTURE, root)
    shared = next(r for r in m["windows"] if r["shared"])
    other = next(r for r in m["windows"] if not r["shared"])
    return run, root, store, shared, other


def save_all(root, name, kw_for):
    m, msha = lc.load_manifest(LECTURE, root)
    rows = lc.windows_for(m, name)
    store = LabelStore(root / LECTURE / f"{name}.json", LECTURE, name, msha, rows,
                       frozenset(lc.accepted_manifest_sha256(m, msha)))
    for r in rows:
        store.save(record(LECTURE, r["window_index"], r["start_s"], r["end_s"], **kw_for(r)))
    return store


def save(store, row, **kw):
    store.save(record(LECTURE, row["window_index"], row["start_s"], row["end_s"], **kw))


def entries(root):
    return json.loads((root / LECTURE / "corrections_bilal.json").read_text())["entries"]


def test_relation_deletion_and_reversal_accepted_on_non_shared_window(env):
    run, root, store, _, other = env
    i = other["window_index"]
    save(store, other, concepts=[concept(f"a{i}"), concept(f"b{i}")], relations=[rel(f"b{i}", "part_of", f"a{i}")])
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1  # unlogged
    with pytest.raises(SystemExit, match="not a shared window"):
        run("log-correction", "--lecture", LECTURE, "--window", str(i), "--reason", "x")  # Amendment 3 only
    assert run("log-correction", "--lecture", LECTURE, "--window", str(i), "--amendment", "4",
               "--reason", "part_of inverted; contrasts_with does not hold") == 0
    assert entries(root)[-1]["amendment"] == 4
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0
    save(store, other, concepts=[concept(f"a{i}"), concept(f"b{i}")], relations=[])
    assert run("log-correction", "--lecture", LECTURE, "--window", str(i), "--amendment", "4",
               "--reason", "deleted") == 0
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0
    assert run("merge", "--lecture", LECTURE) == 0
    gold = {r["window"]["window_index"]: r for r in json.loads((root / LECTURE / "gold.json").read_text())["windows"]}
    assert gold[i]["relations"] == [] and len(gold[i]["concepts"]) == 2


@pytest.mark.parametrize("change", [
    {"concepts": ["a", "c"], "relations": []},                           # concept renamed
    {"concepts": ["a", "b"], "aliases": True, "relations": []},          # alias added
    {"concepts": ["a", "b"], "important": True, "relations": []},        # importance flag changed
    {"concepts": ["a", "b"], "relations": [("a", "example_of", "b")]},  # relation type changed (not a reversal)
])
def test_other_changes_refused_on_non_shared_window(env, change, capsys):
    run, root, store, _, other = env
    i = other["window_index"]
    names = [f"{c}{i}" for c in change["concepts"]]
    cs = [concept(names[0], "alias") if change.get("aliases") else concept(names[0]), concept(names[1])]
    kw = {"important": True, "cue": "this is important"} if change.get("important") else {}
    save(store, other, concepts=cs, relations=[rel(f"{h}{i}", t, f"{tl}{i}") for h, t, tl in change["relations"]],
         **kw)
    with pytest.raises(SystemExit, match="Amendment 4 only deletes or reverses relations"):
        run("log-correction", "--lecture", LECTURE, "--window", str(i), "--amendment", "4", "--reason", "x")
    assert not (root / LECTURE / "corrections_bilal.json").exists()
    capsys.readouterr()
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1
    with pytest.raises(SystemExit):
        run("merge", "--lecture", LECTURE)


def test_validate_refuses_a_hand_edited_amendment4_log_that_changes_a_concept(env, capsys):
    run, root, store, _, other = env
    i = other["window_index"]
    save(store, other, concepts=[concept(f"a{i}"), concept(f"b{i}")], relations=[])
    assert run("log-correction", "--lecture", LECTURE, "--window", str(i), "--amendment", "4", "--reason", "x") == 0
    save(store, other, concepts=[concept(f"a{i}"), concept(f"z{i}")], relations=[])
    path = root / LECTURE / "corrections_bilal.json"
    log = json.loads(path.read_text())
    current = json.loads((root / LECTURE / "bilal.json").read_text())["windows"]
    log["entries"][-1]["after"] = next(r for r in current if r["window"]["window_index"] == i)
    path.write_text(json.dumps(log))
    capsys.readouterr()
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1
    assert "Amendment 4 only deletes or reverses relations" in capsys.readouterr().out


def test_amendment4_only_on_its_lecture(env, monkeypatch):
    run, _, store, _, other = env
    i = other["window_index"]
    save(store, other, concepts=[concept(f"a{i}"), concept(f"b{i}")], relations=[])
    monkeypatch.setattr(lc, "AMENDMENT4_LECTURES", frozenset({"sha256-" + "0" * 32}))
    with pytest.raises(SystemExit, match="Amendment 4 applies only to"):
        run("log-correction", "--lecture", LECTURE, "--window", str(i), "--amendment", "4", "--reason", "x")


def test_shared_window_corrections_unchanged(env):
    run, root, store, shared, other = env
    i = shared["window_index"]
    save(store, shared, concepts=[concept(f"a{i}"), concept(f"renamed{i}", "alias")], relations=[])
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1
    assert run("log-correction", "--lecture", LECTURE, "--window", str(i), "--reason", "clear error") == 0
    assert entries(root)[-1]["amendment"] == 3
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0
    # an Amendment 3 log entry without the `amendment` key (written before Amendment 4) still counts
    path = root / LECTURE / "corrections_bilal.json"
    log = json.loads(path.read_text())
    del log["entries"][-1]["amendment"]
    path.write_text(json.dumps(log))
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0
    # a non-shared window changed by an Amendment 3 entry is still refused
    j = other["window_index"]
    save(store, other, concepts=[concept(f"a{j}"), concept(f"b{j}")], relations=[])
    log["entries"].append({"window_index": j, "reason": "x", "before": None,
                           "after": json.loads((root / LECTURE / "bilal.json").read_text())["windows"][0]})
    path.write_text(json.dumps(log))
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1
