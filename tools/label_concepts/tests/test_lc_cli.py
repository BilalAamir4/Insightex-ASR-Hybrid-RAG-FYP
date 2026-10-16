"""sample -> label -> validate -> agreement -> merge on a synthetic workspace, plus the HTTP server."""

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import label_concepts as lc
import pytest
from extraction_schema import check_document
from grid import build_grid
from lc_fixtures import concept, make_workspace, record, rel, toy_segments
from server import LabelStore, make_handler

LECTURE = "sha256-" + "0" * 32


@pytest.fixture
def env(tmp_path):
    segs = toy_segments(12)
    grid = build_grid(segs, 360)
    index = [{"id": w.index, "start": w.start_s, "end": w.end_s, "text": w.text} for w in grid]
    make_workspace(tmp_path / "data", LECTURE, segs, 360, index_windows=index)
    root = tmp_path / "labels"

    def run(*args):
        return lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(root), *args])

    return run, root, tmp_path


def sample(run, *labellers):
    assert run("sample", "--lecture", LECTURE, "--n", "8", "--shared", "4", "--exclude", "2=guide example",
               "--labellers", *(labellers or ("bilal", "fatima"))) == 0


def write_labels(root, name, manifest, msha, recs):
    rows = lc.windows_for(manifest, name)
    store = LabelStore(root / LECTURE / f"{name}.json", LECTURE, name, msha, rows)
    for r in rows:
        store.save(recs.get(r["window_index"], record(LECTURE, r["window_index"], r["start_s"], r["end_s"])))


def test_sample_writes_manifest_and_refuses_to_overwrite(env):
    run, root, _ = env
    sample(run)
    m, _ = lc.load_manifest(LECTURE, root)
    assert m["grid"]["index_check"] == "match" and m["n_sampled"] == 8 and not m["census"]
    assert m["excluded"] == [{"window_index": 2, "reason": "guide example"}]
    assert "text" not in json.dumps(m["windows"][0]).replace("text_sha256", "")  # no transcript text stored
    with pytest.raises(SystemExit):
        sample(run)


def test_untested_language_is_refused(tmp_path):
    make_workspace(tmp_path / "data", "yt-x", toy_segments(3), 90, tier="untested")
    with pytest.raises(SystemExit, match="untested"):
        lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(tmp_path / "l"), "sample",
                 "--lecture", "yt-x"])


def test_grid_mismatch_with_index_is_refused(tmp_path):
    make_workspace(tmp_path / "data", "yt-y", toy_segments(3), 90,
                   index_windows=[{"id": 0, "start": 0.0, "end": 30.0, "text": "other"}])
    with pytest.raises(SystemExit):
        lc.main(["--data-dir", str(tmp_path / "data"), "--labels-root", str(tmp_path / "l"), "sample",
                 "--lecture", "yt-y"])


def test_validate_agreement_and_merge(env, capsys):
    run, root, _ = env
    sample(run)
    m, msha = lc.load_manifest(LECTURE, root)
    shared = [r for r in m["windows"] if r["shared"]]
    w0, w1 = shared[0], shared[1]
    a_recs = {
        w0["window_index"]: record(LECTURE, w0["window_index"], w0["start_s"], w0["end_s"],
                                   concepts=[concept("batch learning", "offline learning"), concept("online learning")],
                                   relations=[rel("batch learning", "contrasts_with", "online learning")],
                                   important=True, cue="says it is important"),
        w1["window_index"]: record(LECTURE, w1["window_index"], w1["start_s"], w1["end_s"],
                                   concepts=[concept("learning rate")]),
    }
    b_recs = {
        w0["window_index"]: record(LECTURE, w0["window_index"], w0["start_s"], w0["end_s"],
                                   concepts=[concept("Offline Learning"), concept("online learning"),
                                             concept("server")],
                                   relations=[rel("online learning", "contrasts_with", "Offline Learning")]),
    }
    write_labels(root, "bilal", m, msha, a_recs)
    write_labels(root, "fatima", m, msha, b_recs)
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 0
    assert run("agreement", "--lecture", LECTURE, "--a", "bilal", "--b", "fatima") == 0
    report = json.loads((root / LECTURE / "agreement_bilal_fatima.json").read_text())
    mi = report["micro"]
    assert mi["concept"]["tp"] == 2 and mi["concept"]["ref"] == 3 and mi["concept"]["pred"] == 3
    assert mi["relation"]["tp"] == 1
    assert mi["important"]["ref"] == 1 and mi["important"]["pred"] == 0 and mi["important"]["agreement"] == 0.75
    per = {w["window_index"]: w for w in report["per_window"]}
    assert per[w0["window_index"]]["only_b"] == ["server"]
    assert per[w1["window_index"]]["concept_f1"] == 0.0
    assert per[shared[2]["window_index"]]["concept_f1"] == 1.0  # both empty
    assert len(report["inputs"]["bilal"]["sha256"]) == 64
    assert "To discuss" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="no labels file"):
        run("merge", "--lecture", LECTURE)  # no consensus file yet
    write_labels(root, "consensus", m, msha, a_recs)
    assert run("merge", "--lecture", LECTURE) == 0
    gold = json.loads((root / LECTURE / "gold.json").read_text())
    assert check_document(gold) == [] and len(gold["windows"]) == 8
    assert [w["window"]["window_index"] for w in gold["windows"]] == [r["window_index"] for r in m["windows"]]


def test_validate_reports_missing_unassigned_and_stale_manifest(env, capsys):
    run, root, _ = env
    sample(run)
    m, msha = lc.load_manifest(LECTURE, root)
    rows = lc.windows_for(m, "bilal")
    other = next(r for r in m["windows"] if r["assigned_to"] == ["fatima"])
    doc = {"schema_version": 1, "lecture_id": LECTURE, "producer": {"kind": "human", "name": "bilal"},
           "sample_manifest_sha256": "f" * 64,
           "windows": [record(LECTURE, r["window_index"], r["start_s"], r["end_s"]) for r in rows[1:]]
           + [record(LECTURE, other["window_index"], other["start_s"], other["end_s"])]}
    errors = lc.validate_labels(doc, m, msha, "bilal")
    text = "\n".join(errors)
    assert "sample_manifest_sha256" in text and "not assigned to bilal" in text and "not labelled yet" in text
    (root / LECTURE / "bilal.json").write_text(json.dumps(doc))
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal") == 1


@pytest.fixture
def server(env):
    run, root, tmp = env
    sample(run)
    m, msha = lc.load_manifest(LECTURE, root)
    rows = lc.windows_for(m, "bilal")
    store = LabelStore(root / LECTURE / "bilal.json", LECTURE, "bilal", msha, rows)
    video = tmp / "data" / "workspaces" / LECTURE / "stages" / "normalise" / "n1" / "video.mp4"
    handler = make_handler(session={"lecture_id": LECTURE, "labeller": "bilal", "windows": [],
                                    "relation_types": []}, rows={r["window_index"]: r for r in rows},
                           store=store, video=video)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1], rows, store
    httpd.shutdown()
    httpd.server_close()


def request(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, dict(r.getheaders()), data


def test_server_saves_valid_and_rejects_invalid_labels(server):
    port, rows, store = server
    i = rows[0]["window_index"]
    ok = {"concepts": [{"label": "batch learning", "aliases": []}], "relations": [], "important": False, "cue": None}
    status, _, _ = request(port, "PUT", f"/api/window/{i}", json.dumps(ok))
    assert status == 200
    saved = json.loads(store.path.read_text())
    assert saved["windows"][0]["window"]["window_index"] == i and check_document(saved) == []
    bad = {**ok, "relations": [{"head": "batch learning", "type": "part_of", "tail": "nothing"}]}
    status, _, data = request(port, "PUT", f"/api/window/{i}", json.dumps(bad))
    assert status == 400 and "not the label of a concept" in json.loads(data)["errors"][0]
    status, _, _ = request(port, "PUT", "/api/window/9999", json.dumps(ok))
    assert status == 404
    status, _, data = request(port, "GET", "/api/session")
    assert status == 200 and len(json.loads(data)["labels"]) == 1


def test_server_video_ranges(server):
    port, _, _ = server
    status, h, data = request(port, "GET", "/video.mp4")
    assert status == 200 and len(data) == 1024 and h["Accept-Ranges"] == "bytes"
    status, h, data = request(port, "GET", "/video.mp4", headers={"Range": "bytes=10-19"})
    assert status == 206 and data == bytes(range(10, 20)) and h["Content-Range"] == "bytes 10-19/1024"
    status, _, data = request(port, "GET", "/video.mp4", headers={"Range": "bytes=-4"})
    assert status == 206 and data == bytes(range(252, 256))
    status, _, _ = request(port, "GET", "/video.mp4", headers={"Range": "bytes=5000-"})
    assert status == 416


def test_single_labeller_repeat_agreement_and_merge(env):
    run, root, _ = env
    sample(run, "bilal")
    m, msha = lc.load_manifest(LECTURE, root)
    assert m["labellers"] == ["bilal"] and all(r["assigned_to"] == ["bilal"] for r in m["windows"])
    shared = [r for r in m["windows"] if r["shared"]]
    assert [r["window_index"] for r in lc.windows_for(m, "bilal_repeat")] == [r["window_index"] for r in shared]
    w0 = shared[0]
    first = {w0["window_index"]: record(LECTURE, w0["window_index"], w0["start_s"], w0["end_s"],
                                        concepts=[concept("batch learning"), concept("online learning")])}
    repeat = {w0["window_index"]: record(LECTURE, w0["window_index"], w0["start_s"], w0["end_s"],
                                         concepts=[concept("batch learning")])}
    write_labels(root, "bilal", m, msha, first)
    write_labels(root, "bilal_repeat", m, msha, repeat)
    assert run("validate", "--lecture", LECTURE, "--labeller", "bilal_repeat") == 0
    assert run("agreement", "--lecture", LECTURE, "--a", "bilal", "--b", "bilal_repeat") == 0
    report = json.loads((root / LECTURE / "agreement_bilal_bilal_repeat.json").read_text())
    assert len(report["per_window"]) == 4 and report["micro"]["concept"]["tp"] == 1
    assert report["micro"]["concept"]["ref"] == 2 and report["micro"]["concept"]["pred"] == 1
    assert run("merge", "--lecture", LECTURE) == 0  # no consensus file needed
    gold = json.loads((root / LECTURE / "gold.json").read_text())
    assert check_document(gold) == [] and gold["producer"]["name"] == "gold: bilal (single annotator)"
    assert [w["window"]["window_index"] for w in gold["windows"]] == [r["window_index"] for r in m["windows"]]
    assert gold["windows"][0] == first[w0["window_index"]]  # the shared windows come from bilal, not the repeat
    with pytest.raises(SystemExit, match="not in the sample manifest"):
        lc.windows_for(m, "fatima_repeat")


def test_reassign_keeps_windows_and_old_labels_files_stay_valid(env):
    run, root, _ = env
    sample(run)
    old, old_sha = lc.load_manifest(LECTURE, root)
    write_labels(root, "bilal", old, old_sha, {})
    fatima_only = [r["window_index"] for r in old["windows"] if r["assigned_to"] == ["fatima"]]
    with pytest.raises(SystemExit):
        run("reassign", "--lecture", LECTURE, "--labellers", "bilal", "--note", " ")
    assert run("reassign", "--lecture", LECTURE, "--labellers", "bilal", "--note", "ADR-0048 Amendment 1") == 0
    new, new_sha = lc.load_manifest(LECTURE, root)
    assert new_sha != old_sha and new["labellers"] == ["bilal"]
    strip = ("assigned_to",)
    assert [{k: v for k, v in r.items() if k not in strip} for r in new["windows"]] == \
        [{k: v for k, v in r.items() if k not in strip} for r in old["windows"]]
    assert {k: v for k, v in new.items() if k not in ("windows", "labellers", "amendments")} == \
        {k: v for k, v in old.items() if k not in ("windows", "labellers")}
    (amend,) = new["amendments"]
    assert amend["previous_sha256"] == old_sha and amend["labellers_before"] == ["bilal", "fatima"]
    assert amend["newly_assigned"] == {"bilal": fatima_only} and amend["note"] == "ADR-0048 Amendment 1"
    doc, path = lc.load_labels(LECTURE, "bilal", root)
    assert doc["sample_manifest_sha256"] == old_sha
    assert lc.validate_labels(doc, new, new_sha, "bilal", complete=False) == []
    errors = lc.validate_labels(doc, new, new_sha, "bilal")
    assert len(errors) == 1 and f"{len(fatima_only)} assigned window(s) not labelled yet" in errors[0]
    rows = lc.windows_for(new, "bilal")
    store = LabelStore(path, LECTURE, "bilal", new_sha, rows, frozenset(lc.accepted_manifest_sha256(new, new_sha)))
    assert len(store.records) == 8 - len(fatima_only)
    r = next(r for r in rows if r["window_index"] == fatima_only[0])
    store.save(record(LECTURE, r["window_index"], r["start_s"], r["end_s"]))
    assert json.loads(path.read_text())["sample_manifest_sha256"] == new_sha
    with pytest.raises(SystemExit, match="another sample manifest"):
        LabelStore(path, LECTURE, "bilal", "e" * 64, rows)
