"""ADR-0048 Amendment 5 on a synthetic lecture: the relabelling pass of a frozen gold (keep, remove or rename each
concept, every change logged with its reason), gold_v2.json written beside an unchanged gold.json, and scoring
against a chosen gold version with its own adjudications file."""

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import label_concepts as lc
import pytest
import relabel
from extraction_schema import check_document
from grid import build_grid
from lc_fixtures import concept, make_workspace, record, rel, toy_segments, write_run
from server import LabelStore, RelabelStore, make_relabel_handler

LECTURE = "sha256-" + "5" * 32


def labels_for(i):
    if i % 2 == 0:  # two variant names of one idea, a third concept, and relations through all of them
        return {"concepts": [concept("Problem With Batch Learning", "problem of batch learning"),
                             concept("Lots Of Data", "big data"), concept("Server")],
                "relations": [rel("Lots Of Data", "part_of", "Problem With Batch Learning"),
                              rel("Server", "contrasts_with", "Lots Of Data")]}
    return {"concepts": [concept("Problem Of Batch Learning")], "important": True, "cue": "Says remember this."}


@pytest.fixture
def env(tmp_path):
    segs = toy_segments(8)
    grid = build_grid(segs, 240)
    index = [{"id": w.index, "start": w.start_s, "end": w.end_s, "text": w.text} for w in grid]
    make_workspace(tmp_path / "data", LECTURE, segs, 240, index_windows=index)
    root = tmp_path / "labels"

    def run(*args):
        return lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(root), *args])

    assert run("sample", "--lecture", LECTURE, "--n", "6", "--shared", "2", "--labellers", "bilal") == 0
    m, msha = lc.load_manifest(LECTURE, root)
    rows = lc.windows_for(m, "bilal")
    store = LabelStore(root / LECTURE / "bilal.json", LECTURE, "bilal", msha, rows)
    for r in rows:
        store.save(record(LECTURE, r["window_index"], r["start_s"], r["end_s"], **labels_for(r["window_index"])))
    assert run("merge", "--lecture", LECTURE) == 0
    return run, root, tmp_path


def state_and_base(root):
    p = relabel.paths(root / LECTURE, "v2")
    return relabel.load(p["state"], p["base"], LECTURE)


def body(win, reviewed=False, **decisions):
    """decisions: v1 label -> (decision, label, reason)."""
    out = []
    for c in win["concepts"]:
        d, label, reason = decisions.get(c["v1_label"], (c["decision"], c["label"], c["reason"]))
        out.append({"v1_label": c["v1_label"], "decision": d, "label": label, "reason": reason})
    return {"reviewed": reviewed, "concepts": out}


def review_all(root):
    """Even windows: rename the variant, remove "Server" (its relation goes too), keep "Lots Of Data". Odd windows:
    rename to the same canonical name."""
    p = relabel.paths(root / LECTURE, "v2")
    state, base = relabel.load(p["state"], p["base"], LECTURE)
    for w in state["windows"]:
        errors = relabel.update_window(state, base, w["window_index"], body(
            w, reviewed=True,
            **{"Problem With Batch Learning": ("keep", "problem of batch learning", "one canonical name"),
               "Problem Of Batch Learning": ("keep", "problem of batch learning", "one canonical name"),
               "Lots Of Data": ("keep", "Lots Of Data", ""),
               "Server": ("remove", "Server", "named, not explained")}))
        assert errors == []
    relabel.write_atomic(p["state"], state)
    return state, base


def test_start_writes_state_from_frozen_gold_and_refuses_twice(env):
    run, root, _ = env
    gold_sha = lc.sha256_file(root / LECTURE / "gold.json")
    assert run("relabel-start", "--lecture", LECTURE) == 0
    state, base = state_and_base(root)
    assert state["base"] == {"file": "gold.json", "sha256": gold_sha} and state["log"] == []
    assert [w["window_index"] for w in state["windows"]] == [r["window"]["window_index"] for r in base["windows"]]
    assert all(c["decision"] is None and c["label"] == c["v1_label"] for w in state["windows"] for c in w["concepts"])
    with pytest.raises(SystemExit, match="exists"):
        run("relabel-start", "--lecture", LECTURE)


def test_reasons_required_and_every_change_logged(env):
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = next(w for w in state["windows"] if len(w["concepts"]) == 3)
    i = w["window_index"]
    assert "needs a reason" in relabel.update_window(state, base, i, body(w, Server=("remove", "Server", "")))[0]
    assert "needs a reason" in relabel.update_window(
        state, base, i, body(w, **{"Lots Of Data": ("keep", "lots of data", " ")}))[0]
    assert "before the window is marked reviewed" in relabel.update_window(state, base, i, body(w, reviewed=True))[-1]
    assert state["log"] == []  # nothing changed by the refused updates
    errors = relabel.update_window(state, base, i, body(w, Server=("remove", "Server", "named, not explained"),
                                                        **{"Lots Of Data": ("keep", "lots of data", "lower case")}))
    assert errors == []
    fields = {(e["v1_label"], e["field"]): e for e in state["log"]}
    assert fields[("Server", "decision")]["after"] == "remove"
    assert fields[("Server", "decision")]["reason"] == "named, not explained"
    assert fields[("Lots Of Data", "label")]["before"] == "Lots Of Data"
    assert fields[("Lots Of Data", "label")]["after"] == "lots of data"
    n = len(state["log"])
    assert relabel.update_window(state, base, i, body(state["windows"][[x["window_index"] for x in state["windows"]]
                                                                          .index(i)])) == []
    assert len(state["log"]) == n  # saving the same decisions again logs nothing


def test_payload_must_list_the_v1_concepts_and_stay_valid(env):
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = next(w for w in state["windows"] if len(w["concepts"]) == 3)
    b = body(w)
    b["concepts"] = b["concepts"][:2]
    assert any("gold v1 concepts" in e for e in relabel.update_window(state, base, w["window_index"], b))
    b = body(w)
    b["concepts"].append({"v1_label": "new idea", "decision": "keep", "label": "new idea", "reason": "added"})
    assert any("gold v1 concepts" in e for e in relabel.update_window(state, base, w["window_index"], b))
    clash = body(w, Server=("keep", "Lots Of Data", "same name"))  # two concepts with one name: invalid record
    assert any("also a name of concept" in e for e in relabel.update_window(state, base, w["window_index"], clash))
    assert relabel.update_window(state, base, 999, body(w)) == ["window 999 is not a gold window"]


def test_apply_drops_relations_of_removed_and_renames_endpoints_and_aliases():
    base_rec = record(LECTURE, 0, 0.0, 30.0, concepts=[concept("A", "x"), concept("B", "b two"), concept("C")],
                      relations=[rel("A", "part_of", "B"), rel("C", "contrasts_with", "B")])
    out = relabel.apply(base_rec, [
        {"v1_label": "A", "decision": "keep", "label": "x", "reason": "r"},
        {"v1_label": "B", "decision": "keep", "label": "B", "reason": ""},
        {"v1_label": "C", "decision": "remove", "label": "C", "reason": "r"}])
    assert out["concepts"] == [concept("x"), concept("B", "b two")]  # alias "x" became the label
    assert out["relations"] == [rel("x", "part_of", "B")]
    assert base_rec["concepts"][0] == concept("A", "x")  # the base record is not changed


def test_merge_needs_every_window_reviewed_and_leaves_gold_v1_unchanged(env, capsys):
    run, root, _ = env
    gold_v1 = (root / LECTURE / "gold.json").read_bytes()
    run("relabel-start", "--lecture", LECTURE)
    with pytest.raises(SystemExit, match="not marked reviewed"):
        run("relabel-merge", "--lecture", LECTURE)
    review_all(root)
    assert run("relabel-merge", "--lecture", LECTURE) == 0
    assert (root / LECTURE / "gold.json").read_bytes() == gold_v1
    v2 = json.loads((root / LECTURE / "gold_v2.json").read_text())
    assert check_document(v2) == [] and "Amendment 5" in v2["producer"]["name"]
    even = next(r for r in v2["windows"] if r["window"]["window_index"] % 2 == 0)
    odd = next(r for r in v2["windows"] if r["window"]["window_index"] % 2 == 1)
    assert even["concepts"] == [concept("problem of batch learning"), concept("Lots Of Data", "big data")]
    assert even["relations"] == [rel("Lots Of Data", "part_of", "problem of batch learning")]
    assert odd["concepts"] == [concept("problem of batch learning")] and odd["important"] is True
    with pytest.raises(SystemExit, match="exists"):
        run("relabel-merge", "--lecture", LECTURE)
    capsys.readouterr()
    assert run("relabel-status", "--lecture", LECTURE, "--labels") == 0
    out = capsys.readouterr().out
    assert "reviewed 6 of 6" in out and "removed 3" in out and "one concept or several" not in out


def test_changed_base_gold_is_refused(env):
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    path = root / LECTURE / "gold.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="changed since the pass started"):
        run("relabel-status", "--lecture", LECTURE)


def test_possible_variants_flag_names_that_differ_only_in_small_words():
    labels = {"Problem With Batch Learning": [10], "problem of batch learning": [12], "Problems of batch learning":
              [13], "batch learning": [4], "Disadvantages Of Batch Learning": [16]}
    assert relabel.possible_variants(labels) == [
        ["Problem With Batch Learning", "problem of batch learning", "Problems of batch learning"]]


def test_scoring_against_gold_v2_uses_its_own_files(env, tmp_path):
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    review_all(root)
    run("relabel-merge", "--lecture", LECTURE)
    gold = json.loads((root / LECTURE / "gold_v2.json").read_text())
    arm = write_run(tmp_path / "arm", LECTURE, "a", [
        record(LECTURE, r["window"]["window_index"], r["window"]["start_s"], r["window"]["end_s"],
               concepts=[concept("problem of batch learning"), concept("unmatched idea")]) for r in gold["windows"]])
    report = lc.score_report(LECTURE, lc.load_arms([f"a={arm}"]), root, "v2")
    assert report["gold"]["version"] == "v2" and report["gold"]["sha256"] == lc.sha256_file(root / LECTURE /
                                                                                          "gold_v2.json")
    assert report["headline_string_rule"]["inter_annotator_agreement"]["available"] is False
    assert report["arms"][0]["string_rule"]["micro"]["concept"]["tp"] == len(gold["windows"])
    assert run("adjudication-sheet", "--lecture", LECTURE, "--gold", "v2", "--comparison", "C1",
               "--arm", f"a={arm}", "--seed", "1") == 0
    sheets = list((root / LECTURE / "adjudication_sheets").glob("C1-gold_v2-*.json"))
    assert len(sheets) == 1
    sheet = json.loads(sheets[0].read_text())
    assert sheet["gold_sha256"] == report["gold"]["sha256"] and len(sheet["entries"]) == len(gold["windows"])
    with pytest.raises(SystemExit, match="changed since this sheet"):  # a v2 sheet is refused against gold v1
        run("adjudicate", "--lecture", LECTURE, "--sheet", str(sheets[0]))
    assert not (root / LECTURE / "adjudications.json").exists()


# -- the page's server ---------------------------------------------------------------------------------------------


@pytest.fixture
def server(env):
    run, root, tmp = env
    run("relabel-start", "--lecture", LECTURE)
    p = relabel.paths(root / LECTURE, "v2")
    store = RelabelStore(p["state"], p["base"], LECTURE)
    windows = [{"window_index": r["window"]["window_index"], "start_s": r["window"]["start_s"],
                "end_s": r["window"]["end_s"], "shared": False, "text": "t"} for r in store.base["windows"]]
    video = tmp / "data" / "workspaces" / LECTURE / "stages" / "normalise" / "n1" / "video.mp4"
    handler = make_relabel_handler(session={"lecture_id": LECTURE, "pass": "v2", "windows": windows}, store=store,
                                   video=video)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], p["state"]
    httpd.shutdown()
    httpd.server_close()


def request(port, method, path, payload=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=None if payload is None else json.dumps(payload))
    r = c.getresponse()
    data = json.loads(r.read())
    c.close()
    return r.status, data


def test_server_saves_decisions_and_rejects_bad_ones(server):
    port, state_path = server
    status, session = request(port, "GET", "/api/relabel")
    assert status == 200 and session["summary"]["undecided"] > 0
    w = next(w for w in session["windows"] if len(w["concepts"]) == 3)
    assert w["v1"]["concepts"][0]["label"] == "Problem With Batch Learning" and w["v2"] == w["v1"]
    i = w["window_index"]
    status, data = request(port, "PUT", f"/api/relabel/window/{i}", body(w, Server=("remove", "Server", "")))
    assert status == 400 and "needs a reason" in data["errors"][0]
    status, data = request(port, "PUT", f"/api/relabel/window/{i}", body(w, Server=("remove", "Server", "passing")))
    assert status == 200 and [c["label"] for c in data["window"]["v2"]["concepts"]] == [
        "Problem With Batch Learning", "Lots Of Data"]
    saved = json.loads(state_path.read_text())
    assert saved["log"][-1]["v1_label"] == "Server" and saved["log"][-1]["reason"] == "passing"
    status, _ = request(port, "PUT", "/api/relabel/window/999", body(w))
    assert status == 404
