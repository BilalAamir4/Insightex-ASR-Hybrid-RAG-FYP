"""M7 extraction harness (ADR-0048 sections 7 and 8, Amendment 2) on synthetic windows with a fake model client.

No Ollama, no GPU, no real lecture text, no real prompt: the prompt files are placeholders written by the tests.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
from pathlib import Path

import pytest

from insightex.core.config import load_settings
from insightex.extract import harness as h
from insightex.extract.arms import Arm, ArmConfigError, load_arms
from insightex.extract.prompts import PromptNotFrozen, draft_text, extraction_format, load_frozen
from insightex.extract.vram import VramSampler
from insightex.llm.ollama_client import OutputTruncated

LECTURE = "sha256-" + "2" * 32
REPO = Path(__file__).resolve().parents[3]


def windows(n: int) -> list[h.WindowText]:
    return [h.WindowText(i, 30.0 * i, 30.0 * i + 30, f"synthetic window {i} text") for i in range(n)]


def item(i: int, **kw):
    base = {"window_index": i, "concepts": [{"label": f"c{i}", "aliases": []}], "relations": [], "important": False,
            "cue": None, "is_recap": False}
    return {**base, **kw}


def default_respond(user, messages, attempt):
    if "text" in user:  # translation call
        return json.dumps({"english": "EN " + user["text"]})
    return json.dumps({"windows": [item(w["window_index"]) for w in user["windows"]]})


class FakeClient:
    def __init__(self, respond=default_respond):
        self.respond = respond
        self.chats: list[dict] = []
        self.loaded: set[str] = {"some-other-model:latest"}
        self.unloaded: list[str] = []

    def digest(self, model):
        return "digest-" + model

    def chat(self, model, messages, format_schema, num_ctx, num_predict):
        user = json.loads(messages[1]["content"])
        attempt = 1 + sum(1 for c in self.chats if c["messages"] == messages)
        self.chats.append({"model": model, "messages": messages, "format": format_schema, "user": user,
                           "num_ctx": num_ctx, "num_predict": num_predict})
        self.loaded.add(model)
        content = self.respond(user, messages, attempt)
        if isinstance(content, Exception):
            raise content
        return content, {"prompt_eval_count": 50 * len(user.get("windows", [1])), "eval_count": 20,
                         "eval_duration_s": 0.5, "tokens_per_sec": 40.0}

    def resident(self):
        return [{"name": m, "size": 1000, "size_vram": 1000} for m in sorted(self.loaded)]

    def unload(self, model):
        self.unloaded.append(model)
        self.loaded.discard(model)
        return True


class FakeLease:
    def __init__(self):
        self.purposes: list[str] = []

    def __call__(self, purpose):
        self.purposes.append(purpose)
        return contextlib.nullcontext()


def frozen(tmp_path: Path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return load_frozen(p, hashlib.sha256(text.encode()).hexdigest(), name)


@pytest.fixture
def setup(tmp_path):
    settings = load_settings()
    prompts = h.Prompts(frozen(tmp_path, "prompt.txt", "PLACEHOLDER EXTRACTION PROMPT\n"),
                        frozen(tmp_path, "context.txt", "PLACEHOLDER CONTEXT BLOCK\n"),
                        frozen(tmp_path, "translate.txt", "PLACEHOLDER TRANSLATION PROMPT\n"))

    def ctx(client=None, lease=None, s=settings):
        return h.RunContext(settings=s, client=client or FakeClient(), cache=h.ReplyCache(tmp_path / "cache"),
                            lease=lease or FakeLease(), sampler=VramSampler(0.01, read=lambda: 1000))

    return settings, prompts, ctx


def arm(name="A", **kw):
    base = {"name": name, "comparison": "C1", "model": "qwen3.5:latest", "input": "original", "batch_k": 1,
            "context": "none"}
    return Arm(**{**base, **kw})


# -- planning ------------------------------------------------------------------------------------------------------


def test_plan_batches_and_previous_window_context():
    grid = {w.window_index: w for w in windows(12)}
    plans = h.plan_calls([0, 1, 2, 3, 5, 6, 9], grid, 3, use_context=True)
    assert [p.targets for p in plans] == [(0, 1, 2), (3, 5, 6), (9,)]
    assert plans[0].context == ()  # window 0 has no previous window; 1 and 2 follow their predecessor in the call
    assert plans[1].context == ((2, 3), (4, 5))  # first window's previous, and 5's (4 is not in the call)
    assert plans[2].context == ((8, 9),)
    single = h.plan_calls([4, 1], grid, 1, use_context=False)
    assert [p.targets for p in single] == [(1,), (4,)] and all(p.context == () for p in single)


# -- running -------------------------------------------------------------------------------------------------------


def test_single_window_run_drops_dangling_and_writes_valid_records(setup):
    settings, prompts, ctx = setup

    def respond(user, messages, attempt):
        i = user["windows"][0]["window_index"]
        return json.dumps({"windows": [item(i, concepts=[{"label": "a", "aliases": ["A1"]}, {"label": "b", "aliases": []}],
                                            relations=[{"head": "a", "type": "part_of", "tail": "b"},
                                                       {"head": "a", "type": "example_of", "tail": "ghost"}])]})

    client, lease = FakeClient(respond), FakeLease()
    c = ctx(client, lease)
    doc, run = h.run_arm(c, arm(), prompts, LECTURE, windows(4), [3, 1])
    assert [r["window"]["window_index"] for r in doc["windows"]] == [1, 3]
    assert doc["producer"] == {"kind": "model", "name": "A (qwen3.5:latest)"}
    assert all(r["relations"] == [{"head": "a", "type": "part_of", "tail": "b"}] for r in doc["windows"])
    assert [w["dropped_relations"] for w in run["windows"]] == [1, 1] and run["totals"]["dropped_relations"] == 2
    assert all(w["valid"] and w["attempt_used"] == 1 for w in run["windows"])
    assert lease.purposes == ["m7-eval:A"]
    assert client.unloaded[0] == "some-other-model:latest" and client.unloaded[-1] == "qwen3.5:latest"
    assert client.chats[0]["num_ctx"] == settings.extract.num_ctx
    assert client.chats[0]["format"] == extraction_format([1])
    assert client.chats[0]["user"] == {"windows": [{"window_index": 1, "text": "synthetic window 1 text"}]}
    assert run["prompt_sha256"] == prompts.extraction.sha256 and run["model_digest"] == "digest-qwen3.5:latest"
    assert run["cost"]["vram"]["peak_mib"] == 1000 and run["cost"]["ollama_ps_at_largest_prompt"]["gpu_pct"] == 100.0


def test_invalid_first_reply_is_retried_once(setup):
    _, prompts, ctx = setup

    def respond(user, messages, attempt):
        i = user["windows"][0]["window_index"]
        if i == 0:  # important without a cue on the first attempt, fixed on the retry
            return json.dumps({"windows": [item(0, important=True, cue="said so" if attempt == 2 else None)]})
        if i == 1:  # never valid
            return json.dumps({"windows": [item(1, concepts=[{"label": "x", "aliases": ["X"]}])]})
        return "not json at all" if attempt == 1 else json.dumps({"windows": [item(2)]})

    client = FakeClient(respond)
    doc, run = h.run_arm(ctx(client), arm(), prompts, LECTURE, windows(3), [0, 1, 2])
    status = {w["window_index"]: w for w in run["windows"]}
    assert status[0]["valid"] and status[0]["attempt_used"] == 2
    assert not status[1]["valid"] and status[1]["attempt_used"] is None and len(status[1]["errors"]) == 2
    assert status[2]["valid"] and status[2]["attempt_used"] == 2 and "not JSON" in status[2]["errors"][0][0]
    assert [r["window"]["window_index"] for r in doc["windows"]] == [0, 2]
    assert len(client.chats) == 6  # three calls, each made twice; never a third attempt
    assert run["totals"]["invalid_windows"] == 1 and run["totals"]["retried_windows"] == 2


def test_batch_keeps_first_valid_record_and_retries_only_for_the_rest(setup):
    _, prompts, ctx = setup

    def respond(user, messages, attempt):
        a, b = (w["window_index"] for w in user["windows"])
        first = item(a, concepts=[{"label": f"first{attempt}", "aliases": []}])
        second = item(b) if attempt == 2 else item(b, cue="cue without importance")
        return json.dumps({"windows": [first, second]})

    doc, run = h.run_arm(ctx(FakeClient(respond)), arm(batch_k=2), prompts, LECTURE, windows(2), [0, 1])
    recs = {r["window"]["window_index"]: r for r in doc["windows"]}
    assert recs[0]["concepts"][0]["label"] == "first1"  # attempt 1's valid record is kept
    assert [w["attempt_used"] for w in run["windows"]] == [1, 2]


def test_truncated_reply_is_an_invalid_attempt(setup):
    _, prompts, ctx = setup

    def respond(user, messages, attempt):
        return OutputTruncated(1024, 1024) if attempt == 1 else default_respond(user, messages, attempt)

    _, run = h.run_arm(ctx(FakeClient(respond)), arm(), prompts, LECTURE, windows(1), [0])
    assert run["windows"][0]["attempt_used"] == 2 and "truncated" in run["windows"][0]["errors"][0][0]


def test_cache_reuses_replies_and_keys_cover_settings_and_prompt(setup, tmp_path):
    settings, prompts, ctx = setup
    client = FakeClient()
    h.run_arm(ctx(client), arm(), prompts, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 2
    _, run = h.run_arm(ctx(client), arm(), prompts, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 2 and run["totals"]["cache_hits"] == 2 and run["cost"]["measured"] is False
    other = load_settings({"extract": {"num_ctx": settings.extract.num_ctx // 2}})
    h.run_arm(ctx(client, s=other), arm(), prompts, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 4
    changed = h.Prompts(frozen(tmp_path, "prompt2.txt", "PLACEHOLDER v2\n"), None, None)
    h.run_arm(ctx(client), arm(), changed, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 6
    h.run_arm(ctx(client), arm(model="other:tag"), prompts, LECTURE, windows(2), [0, 1])
    assert len(client.chats) == 8


def test_context_arm_marks_context_and_first_window_equals_arm_a(setup):
    _, prompts, ctx = setup
    client = FakeClient()
    c = ctx(client)
    h.run_arm(c, arm("W"), prompts, LECTURE, windows(3), [0, 2])
    _, run = h.run_arm(c, arm("P", context="previous"), prompts, LECTURE, windows(3), [0, 2])
    assert len(client.chats) == 3  # window 0 under arm P is byte-identical to arm W, so it comes from the cache
    last = client.chats[-1]
    assert last["user"]["context"] == [{"window_index": 1, "precedes_window_index": 2, "text": "synthetic window 1 text"}]
    assert last["messages"][0]["content"].endswith("PLACEHOLDER CONTEXT BLOCK\n")
    assert run["context_block_sha256"] == prompts.context_block.sha256 and len(run["system_message_sha256"]) == 2


def test_english_arm_translates_targets_and_context_and_fails_closed(setup):
    _, prompts, ctx = setup

    def respond(user, messages, attempt):
        if "text" in user and user["text"].startswith("synthetic window 2"):
            return json.dumps({"english": " "})  # blank: a failed translation, both attempts
        return default_respond(user, messages, attempt)

    client = FakeClient(respond)
    _, run = h.run_arm(ctx(client), arm(input="english", context="previous"), prompts, LECTURE, windows(4), [1, 3])
    translated = [c["user"]["text"] for c in client.chats if "text" in c["user"]]
    assert translated.count("synthetic window 2 text") == 2  # retried once
    extraction = [c for c in client.chats if "windows" in c["user"]]
    assert extraction[0]["user"]["windows"][0]["text"] == "EN synthetic window 1 text"
    assert extraction[0]["user"]["context"][0]["text"] == "EN synthetic window 0 text"
    status = {w["window_index"]: w for w in run["windows"]}
    assert status[1]["valid"] and not status[3]["valid"]  # window 3 needs window 2 as context
    assert "no English translation" in status[3]["errors"][0][0]
    assert run["translation_prompt_sha256"] == prompts.translation.sha256


def test_model_is_unloaded_when_the_run_fails(setup):
    _, prompts, ctx = setup

    class Boom(Exception):
        pass

    def respond(user, messages, attempt):
        return Boom("connection lost")

    client = FakeClient(respond)
    with pytest.raises(Boom):
        h.run_arm(ctx(client), arm(), prompts, LECTURE, windows(1), [0])
    assert client.unloaded[-1] == "qwen3.5:latest"


def test_unset_arm_fields_refuse_to_run(setup):
    _, prompts, ctx = setup
    with pytest.raises(ArmConfigError, match="unset"):
        h.run_arm(ctx(), arm(model=None), prompts, LECTURE, windows(1), [0])


# -- inputs, prompts, arms -------------------------------------------------------------------------------------------


def test_prompt_freeze_is_enforced(tmp_path):
    p = tmp_path / "p.txt"
    p.write_text("x")
    with pytest.raises(PromptNotFrozen, match="no frozen"):
        load_frozen(None, None, "extraction prompt")
    with pytest.raises(PromptNotFrozen, match="new freeze"):
        load_frozen(p, "0" * 64, "extraction prompt")
    assert draft_text(p).sha256 == hashlib.sha256(b"x").hexdigest()
    with pytest.raises(PromptNotFrozen):
        h.load_prompts(load_settings(), arm())  # the shipped config has no frozen prompt yet


def test_targets_from_sample_manifest_are_checked_against_the_grid(tmp_path):
    grid = {w.window_index: w for w in windows(3)}
    rows = [{"window_index": i, "start_s": grid[i].start_s, "end_s": grid[i].end_s,
             "text_sha256": hashlib.sha256(grid[i].text.encode()).hexdigest()} for i in (2, 0)]
    f = tmp_path / "sample.json"
    f.write_text(json.dumps({"windows": rows}))
    assert h.load_targets(f, grid) == [0, 2]
    rows[0]["text_sha256"] = "f" * 64
    f.write_text(json.dumps({"windows": rows}))
    with pytest.raises(h.HarnessError, match="text differs"):
        h.load_targets(f, grid)
    f.write_text(json.dumps([0, 7]))
    with pytest.raises(h.HarnessError, match="not in the lecture's grid"):
        h.load_targets(f, grid)


def test_shipped_arms_file_loads(tmp_path):
    arms = load_arms(load_settings().extract.arms_file)
    assert {a.comparison for a in arms.values()} == {"C1", "C2", "C3", "C4"}
    assert not arms["C1-qwen3.5"].missing() and arms["C3-batch"].missing()
    assert arms["C4-previous"].context == "previous"
    bad = tmp_path / "arms.yaml"
    bad.write_text("arms:\n  - {name: ../x, comparison: C1, model: m, input: original, batch_k: 1, context: none}\n")
    with pytest.raises(ArmConfigError):
        load_arms(bad)


# -- CLI and the scorer contract --------------------------------------------------------------------------------------


def test_cli_run_with_fixture_windows_writes_evidence_the_scorer_reads(tmp_path, monkeypatch):
    from insightex.extract import cli

    prompt = tmp_path / "prompt.txt"
    prompt.write_text("PLACEHOLDER\n")
    win_file = tmp_path / "windows.json"
    win_file.write_text(json.dumps({"schema_version": 2, "windows": [
        {"id": w.window_index, "start": w.start_s, "end": w.end_s, "text": w.text} for w in windows(3)]}))
    targets = tmp_path / "targets.json"
    targets.write_text("[0, 1, 2]")
    s = load_settings({"extract": {"prompt_file": str(prompt),
                                   "prompt_sha256": hashlib.sha256(b"PLACEHOLDER\n").hexdigest()},
                       "gpu": {"lease_enabled": False}})
    monkeypatch.setattr(cli, "load_settings", lambda: s)
    monkeypatch.setattr(cli, "VramSampler", lambda interval: VramSampler(interval, read=lambda: None))
    out = tmp_path / "run" / "C1-qwen3.5"
    args = ["run", "--arm", "C1-qwen3.5", "--lecture", LECTURE, "--targets", str(targets), "--windows", str(win_file),
            "--out", str(out)]
    assert cli.main(args, client=FakeClient()) == 0
    assert cli.main(args, client=FakeClient()) == 1  # an existing run is not replaced without --force
    assert cli.main([*args, "--force"], client=FakeClient()) == 0
    calls = (out / "calls.jsonl").read_text().splitlines()
    assert len(calls) == 3 and all(json.loads(c)["cache_hit"] for c in calls)

    sys.path.insert(0, str(REPO / "tools" / "label_concepts"))
    try:
        import scoring
    finally:
        sys.path.pop(0)
    gold = {"schema_version": 1, "lecture_id": LECTURE, "producer": {"kind": "human", "name": "gold: test"},
            "windows": [{"window": {"lecture_id": LECTURE, "window_index": i, "start_s": 30.0 * i,
                                    "end_s": 30.0 * i + 30}, "concepts": [{"label": f"c{i}", "aliases": []}],
                         "relations": [], "important": False, "cue": None} for i in range(3)]}
    score = scoring.score_arm(scoring.load_arm_run("C1-qwen3.5", out), gold, {})
    assert score["validity"]["valid"] and score["adjudicated"]["micro"]["concept"]["f1"] == 1.0


# -- worst-case measurement (Session 2b tool) -------------------------------------------------------------------------


def uneven_windows() -> list[h.WindowText]:
    lengths = [10, 200, 30, 180, 20, 5]  # window 1 is the largest; 2+1 is the largest window-with-previous pair
    return [h.WindowText(i, 30.0 * i, 30.0 * i + 30, "x" * n) for i, n in enumerate(lengths)]


def test_worst_case_selection():
    from insightex.extract.measure import worst_case

    ws = uneven_windows()
    assert worst_case(ws, 1, False).targets == (1,)
    c = worst_case(ws, 1, True)
    assert c.targets == (2,) and c.context_pairs == ((1, 2),)  # 30 + 200 beats 200 + 10
    c = worst_case(ws, 3, True)
    assert c.targets == (1, 2, 3) and c.context_pairs == ((0, 1), (1, 2), (2, 3)) and "upper bound" in c.note
    with pytest.raises(ValueError):
        worst_case(ws, 7, False)


def test_measurement_budget_gpu_share_and_cli(tmp_path, monkeypatch):
    from insightex.extract import cli

    class PartialGpuClient(FakeClient):
        def resident(self):  # at the larger context the model spills to the CPU
            big = any(c["num_ctx"] >= 8192 for c in self.chats[-1:])
            return [{"name": m, "size": 1000, "size_vram": 900 if big else 1000} for m in sorted(self.loaded)]

    prompt = tmp_path / "draft.txt"
    prompt.write_text("DRAFT PLACEHOLDER\n")
    block = tmp_path / "block.txt"
    block.write_text("BLOCK PLACEHOLDER\n")
    win_file = tmp_path / "windows.json"
    win_file.write_text(json.dumps({"windows": [{"id": w.window_index, "start": w.start_s, "end": w.end_s,
                                                  "text": w.text} for w in uneven_windows()]}))
    s = load_settings({"gpu": {"lease_enabled": False}})
    monkeypatch.setattr(cli, "load_settings", lambda: s)
    monkeypatch.setattr(cli, "VramSampler", lambda interval: VramSampler(interval, read=lambda: 2000))
    out = tmp_path / "measure.json"
    client = PartialGpuClient()
    assert cli.main(["measure", "--lecture", LECTURE, "--model", "qwen3.5:latest", "--prompt-file", str(prompt),
                     "--context-block-file", str(block), "--k", "1", "3", "--context", "both",
                     "--num-ctx", "256", "4096", "8192", "--num-predict", "200", "--windows", str(win_file),
                     "--out", str(out)], client=client) == 0
    report = json.loads(out.read_text())
    assert report["prompt"]["frozen"] is False and len(report["cases"]) == 4
    runs = {(c["k"], c["context"], r["num_ctx"]): r for c in report["cases"] for r in c["runs"]}
    assert runs[(1, False, 256)]["sent"] is False  # the estimate already breaks the budget rule
    assert runs[(1, False, 4096)]["passes"] and runs[(3, True, 4096)]["passes"]
    assert not runs[(1, False, 8192)]["passes"] and runs[(1, False, 8192)]["reason"].endswith("100% GPU")
    assert {"k": 3, "context": True} in report["summary_by_num_ctx"]["4096"]["passing"]
    sent = client.chats
    assert len(sent) == 8 and all(c["num_predict"] == 200 for c in sent)
    ctx_call = next(c for c in sent if "context" in c["user"])
    assert ctx_call["messages"][0]["content"].endswith("BLOCK PLACEHOLDER\n")
    assert "x" * 30 not in out.read_text()  # window text is never written to the report
