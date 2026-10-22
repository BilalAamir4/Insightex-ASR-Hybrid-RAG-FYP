"""ADR-0048 Amendment 6 on a synthetic lecture: adding concepts in the gold v2 relabelling pass (label, aliases and a
required reason; no relations), logged like the other changes, validated like any record, and a state written before
Amendment 6 (no "added" lists) still loads with its decisions."""

import json

import pytest
import relabel
from lc_fixtures import concept
from test_lc_amendment5 import (  # noqa: F401 - pytest fixtures
    LECTURE,
    body,
    env,
    request,
    server,
    state_and_base,
)

ADD = {"id": "a1", "label": "online learning", "aliases": ["آن لائن لرننگ", " "], "reason": "explained here"}


def with_added(win, *added, **decisions):
    return {**body(win, **decisions), "added": [dict(a) for a in added]}


def three(state):
    return next(w for w in state["windows"] if len(w["concepts"]) == 3)


def test_added_concept_joins_the_record_without_relations_and_is_logged(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = three(state)
    assert relabel.update_window(state, base, w["window_index"], with_added(w, ADD)) == []
    rec = relabel.derived(state, base)[w["window_index"]]
    assert rec["concepts"][-1] == concept("online learning", "آن لائن لرننگ")  # blank alias dropped
    assert len(rec["relations"]) == 2  # the v1 relations only
    entry = state["log"][-1]
    assert entry["field"] == "added" and entry["added_id"] == "a1" and entry["before"] is None
    assert entry["after"] == {"label": "online learning", "aliases": ["آن لائن لرننگ"]}
    assert entry["reason"] == "explained here"
    assert relabel.summary(state, base)["added"] == 1


def test_changes_and_withdrawal_of_an_addition_are_logged(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = three(state)
    i = w["window_index"]
    relabel.update_window(state, base, i, with_added(w, ADD))
    relabel.update_window(state, base, i, with_added(w, {**ADD, "label": "incremental learning"}))
    assert state["log"][-1]["field"] == "added_label" and state["log"][-1]["after"] == "incremental learning"
    n = len(state["log"])
    relabel.update_window(state, base, i, with_added(w, {**ADD, "label": "incremental learning"}))
    assert len(state["log"]) == n  # the same additions again log nothing
    relabel.update_window(state, base, i, with_added(w))
    assert state["log"][-1]["field"] == "added" and state["log"][-1]["after"] is None
    assert relabel.derived(state, base)[i]["concepts"][-1]["label"] == "Server"


def test_body_without_added_keeps_the_additions(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = three(state)
    relabel.update_window(state, base, w["window_index"], with_added(w, ADD))
    assert relabel.update_window(state, base, w["window_index"], body(w, reviewed=False)) == []
    assert [a["id"] for a in w["added"]] == ["a1"]


@pytest.mark.parametrize("item, message", [
    ({**ADD, "reason": " "}, "needs a reason"),
    ({**ADD, "label": ""}, "needs a label"),
    ({**ADD, "label": "Lots Of Data"}, "also a name of concept"),          # a v1 concept's name
    ({**ADD, "label": "x", "aliases": ["big data"]}, "also a name of concept"),  # a v1 concept's alias
    ({**ADD, "aliases": ["Online Learning"]}, "repeats a name of the same concept"),
    ({**ADD, "id": ""}, "needs its own id"),
    ({"id": "a1", "label": "x", "reason": "r"}, "needs exactly id, label, aliases and reason"),
])
def test_invalid_additions_are_refused_and_change_nothing(env, item, message):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = three(state)
    errors = relabel.update_window(state, base, w["window_index"], with_added(w, item))
    assert any(message in e for e in errors), errors
    assert state["log"] == [] and w["added"] == []


def test_duplicate_added_ids_and_two_additions_with_one_name_are_refused(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = three(state)
    errors = relabel.update_window(state, base, w["window_index"], with_added(w, ADD, {**ADD, "label": "y"}))
    assert any("needs its own id" in e for e in errors)
    errors = relabel.update_window(state, base, w["window_index"], with_added(w, ADD, {**ADD, "id": "a2"}))
    assert any("also a name of concept" in e for e in errors)


def test_addition_can_take_the_name_of_a_removed_concept(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    state, base = state_and_base(root)
    w = three(state)
    assert relabel.update_window(state, base, w["window_index"], with_added(
        w, {**ADD, "label": "Server"}, Server=("remove", "Server", "named, not explained"))) == []


def test_state_written_before_amendment_6_loads_and_keeps_its_decisions(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    p = relabel.paths(root / LECTURE, "v2")
    state, base = relabel.load(p["state"], p["base"], LECTURE)
    w = three(state)
    relabel.update_window(state, base, w["window_index"], body(w, Server=("remove", "Server", "passing")))
    for x in state["windows"]:
        del x["added"]  # the layout before Amendment 6
    relabel.write_atomic(p["state"], state)
    state, base = relabel.load(p["state"], p["base"], LECTURE)
    assert relabel.summary(state, base)["removed"] == 1 and relabel.summary(state, base)["added"] == 0
    w = three(state)
    assert relabel.update_window(state, base, w["window_index"], with_added(w, ADD)) == []
    assert w["concepts"][2]["decision"] == "remove"


def test_merge_writes_added_concepts(env):  # noqa: F811
    run, root, _ = env
    run("relabel-start", "--lecture", LECTURE)
    p = relabel.paths(root / LECTURE, "v2")
    state, base = relabel.load(p["state"], p["base"], LECTURE)
    for w in state["windows"]:
        decided = {c["v1_label"]: ("keep", c["v1_label"], "") for c in w["concepts"]}
        extra = [ADD] if len(w["concepts"]) == 3 else []
        assert relabel.update_window(state, base, w["window_index"],
                                     with_added(w, *extra, reviewed=True, **decided)) == []
    relabel.write_atomic(p["state"], state)
    assert run("relabel-merge", "--lecture", LECTURE) == 0
    v2 = json.loads((root / LECTURE / "gold_v2.json").read_text())
    assert sum(c["label"] == "online learning" for r in v2["windows"] for c in r["concepts"]) == 3


def test_server_saves_an_addition(server):  # noqa: F811
    port, state_path = server
    _, session = request(port, "GET", "/api/relabel")
    w = next(w for w in session["windows"] if len(w["concepts"]) == 3)
    status, data = request(port, "PUT", f"/api/relabel/window/{w['window_index']}", with_added(w, {**ADD, "reason": ""}))
    assert status == 400 and "needs a reason" in " ".join(data["errors"])
    status, data = request(port, "PUT", f"/api/relabel/window/{w['window_index']}", with_added(w, ADD))
    assert status == 200 and data["window"]["added"][0]["id"] == "a1" and data["summary"]["added"] == 1
    assert json.loads(state_path.read_text())["log"][-1]["field"] == "added"
