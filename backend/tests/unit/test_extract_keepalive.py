"""ADR-0056: the keep-alive session (`insightex extract-eval keepalive`) on a fake Ollama and a synthetic workspace.

The fake loads the model on a call when it is not resident (load_duration 6 s) and keeps it only for keep_alive > 0,
like Ollama. Windows, records and the synthetic case are synthetic; no lecture text and no real model.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from extract_fakes import FROZEN_DIGEST, FROZEN_VERSION, record, reply, target_of

from insightex.core.config import load_settings
from insightex.extract import keepalive as ka
from insightex.extract import stage as extract_stage
from insightex.extract.calls import (
    SELF_TEST_FORMAT,
    CallPlan,
    OllamaModelClient,
    WindowText,
    parse_reply,
)
from insightex.extract.prompts import load_frozen
from insightex.llm.ollama_client import OllamaError, PromptTooLong

DAY4 = "sha256-de27cb67c2acbedebd0c2c7416932b8a"
INDEX_KEY, REF_KEY = "1111111111111111", "a92d9cabba3b68fe"
TEXTS = ["یہ پہلی مصنوعی ونڈو ہے۔", "دوسری مصنوعی ونڈو، gradient descent۔", "تیسری مصنوعی ونڈو۔"]
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
CASE_CONTENT = {"k1": json.dumps({"windows": [{"window_index": 18}]}),
                "k3": json.dumps({"windows": [{"window_index": 18}, {"window_index": 20}]})}


def case_body(targets: list[int]) -> dict[str, Any]:
    fmt = {"type": "object", "properties": {"case": {"enum": [len(targets)]}}}
    return {"model": "gemma4:e4b", "messages": [{"role": "system", "content": "placeholder"},
                                                 {"role": "user", "content": f"synthetic {targets}"}],
            "stream": False, "think": False, "format": fmt,
            "options": {"num_ctx": 8192, "temperature": 0.0, "seed": 42, "num_predict": 1024 * len(targets)}}


def write_case_file(path: Path) -> str:
    doc = {"cases": [{"name": n, "targets": t, "body": case_body(t),
                      "reference_sha256": hashlib.sha256(CASE_CONTENT[n].encode()).hexdigest()}
                     for n, t in (("k1", [18]), ("k3", [18, 20, 21]))]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_env(tmp_path: Path, **keepalive: Any):
    case_file = tmp_path / "case.json"
    case_sha = write_case_file(case_file)
    settings = load_settings({"extract": {"vram_poll_interval_s": 0.01, "keepalive": {
        "synthetic_case_file": str(case_file), "synthetic_case_sha256": case_sha,
        "out_dir": str(tmp_path / "evidence"), **keepalive}}})
    ws = settings.jobs.workspaces_dir / DAY4
    (ws / "stages" / "index" / INDEX_KEY).mkdir(parents=True)
    windows = [{"id": i, "start": 30.0 * i, "end": 30.0 * i + 30, "text": t} for i, t in enumerate(TEXTS)]
    (ws / "stages" / "index" / INDEX_KEY / "windows.json").write_text(json.dumps({"windows": windows}),
                                                                       encoding="utf-8")
    grid = {i: WindowText(i, 30.0 * i, 30.0 * i + 30, t) for i, t in enumerate(TEXTS)}
    recs = [parse_reply(reply(record(i)), None, CallPlan((i,), ()), DAY4, grid, drop_self=True)[i].record
            for i in grid]
    (ws / "stages" / "extract" / REF_KEY).mkdir(parents=True)
    (ws / "stages" / "extract" / REF_KEY / "extraction.json").write_text(json.dumps({"windows": recs}),
                                                                          encoding="utf-8")
    (ws / "manifest.json").write_text(json.dumps({"stages": {"index": {"key": INDEX_KEY},
                                                             "extract": {"key": REF_KEY}}}), encoding="utf-8")
    return settings


class FakeOllama:
    """Ollama-like residency: keep_alive 0 unloads after the call; >0 keeps the model (expires 10 min later)."""

    def __init__(self) -> None:
        self.resident_models: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.unloads: list[str] = []
        # (run index of this item, part, item) -> content override; part "day4" item = window index
        self.change: dict[tuple[int, str, Any], str] = {}
        self.fail_on: tuple[int, str, Any] | None = None
        self.extra_model_after: int | None = None  # number of calls after which qwen3.5 appears
        self.force_load_at: int | None = None  # call number whose load_duration is 6 s although resident
        self.seen: dict[tuple[str, Any], int] = {}

    def version(self) -> str:
        return FROZEN_VERSION

    def digest(self, model: str) -> str:
        return FROZEN_DIGEST

    def resident(self) -> list[dict[str, Any]]:
        return [dict(m) for m in self.resident_models]

    def unload(self, model: str) -> bool:
        self.unloads.append(model)
        self.resident_models = [m for m in self.resident_models if m["name"] != model]
        return True

    def chat(self, model, messages, format_schema, num_ctx, num_predict, *, keep_alive, truncate,
             temperature=None, seed=None):
        if format_schema == SELF_TEST_FORMAT:
            raise PromptTooLong(3100, num_ctx, "exceeds")
        if "case" in format_schema.get("properties", {}):
            part, item = "synthetic", "k1" if format_schema["properties"]["case"]["enum"] == [1] else "k3"
        else:
            part, item = "day4", target_of(format_schema)
        n = self.seen.get((part, item), 0)
        self.seen[(part, item)] = n + 1
        self.calls.append({"part": part, "item": item, "keep_alive": keep_alive, "truncate": truncate,
                           "temperature": temperature, "seed": seed, "messages": messages, "num_predict": num_predict})
        if self.fail_on == (n, part, item):
            raise OllamaError("connection lost")
        loaded = any(m["name"] == model for m in self.resident_models)
        load = 0.01 if loaded else 6.0
        if self.force_load_at == len(self.calls):
            load = 6.0
        if keep_alive == 0:
            self.resident_models = [m for m in self.resident_models if m["name"] != model]
        elif not loaded:
            self.resident_models.append({"name": model, "digest": FROZEN_DIGEST, "context_length": num_ctx,
                                         "expires_at": (NOW + timedelta(minutes=10)).isoformat()})
        if self.extra_model_after is not None and len(self.calls) >= self.extra_model_after:
            self.resident_models.append({"name": "qwen3.5:latest"})
            self.extra_model_after = None
        content = self.change.get((n, part, item))
        if content is None:
            content = reply(record(item)) if part == "day4" else CASE_CONTENT[item]
        return content, {"load_duration_s": load, "prompt_eval_count": 900, "eval_count": 60,
                         "eval_duration_s": 0.5, "done_reason": "stop"}


class Vram:
    """Baseline 1000 MiB with nothing loaded, 6000 MiB with Gemma resident (unless `drop` says otherwise)."""

    def __init__(self, fake: FakeOllama) -> None:
        self.fake, self.drop = fake, False

    def __call__(self) -> int:
        if self.drop:
            return 1500
        return 6000 if self.fake.resident_models else 1000


def session(tmp_path, fake=None, lecture=DAY4, **keepalive):
    settings = build_env(tmp_path, **keepalive)
    fake = fake or FakeOllama()
    vram = Vram(fake)
    leases: list[str] = []

    @contextlib.contextmanager
    def lease(purpose):
        leases.append(purpose)
        yield

    result = ka.run_session(settings, fake, lecture, lease, vram, now=lambda: NOW)
    return result, fake, settings, leases


def out_folder(settings) -> Path:
    (folder,) = list(settings.extract.keepalive.out_dir.iterdir())
    return folder


def tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# -- a clean pass --------------------------------------------------------------------------------------------------


def test_identical_replies_pass_with_the_planned_order_and_keep_alive(tmp_path):
    result, fake, _settings, leases = session(tmp_path)
    assert result["outcome"] == "pass", result["void_cause"]
    assert leases == [ka.PURPOSE]
    seq = [(r["run"], r["order"], r["keep_alive"]) for r in result["runs"]]
    assert seq == [("run0", [0, 1, 2], 0), ("synthetic_reference", ["k1", "k3"], 0),
                   ("day4_repeat_1", [0, 1, 2], 600), ("day4_repeat_2", [0, 1, 2], 600),
                   ("day4_repeat_3", [2, 1, 0], 600), ("synthetic_repeat_1", ["k1", "k3"], 600),
                   ("synthetic_repeat_2", ["k1", "k3"], 600), ("synthetic_repeat_3", ["k3", "k1"], 600)]
    t = result["totals"]
    assert (t["calls"], t["repeat_calls"], t["repeat_calls_identical"], t["differences"]) == (20, 15, 15, 0)
    assert fake.unloads[-1] == "gemma4:e4b" and fake.resident_models == []


def test_day4_requests_are_the_stage_requests_and_the_case_is_sent_as_frozen(tmp_path):
    _result, fake, settings, _ = session(tmp_path)
    prompt = load_frozen(settings.extract.prompt_file, settings.extract.prompt_sha256, "extraction prompt")
    for c in fake.calls:
        if c["part"] == "day4":
            w = WindowText(c["item"], 30.0 * c["item"], 30.0 * c["item"] + 30, TEXTS[c["item"]])
            messages, _, num_predict = extract_stage.window_request(settings, prompt, w)
            assert c["messages"] == messages and c["num_predict"] == num_predict
            assert c["truncate"] is settings.extract.truncate and c["temperature"] is None
        else:
            body = case_body([18] if c["item"] == "k1" else [18, 20, 21])
            assert c["messages"] == body["messages"] and c["num_predict"] == body["options"]["num_predict"]
            assert c["truncate"] is None and (c["temperature"], c["seed"]) == (0.0, 42)


def test_the_real_client_sends_the_stage_body_except_keep_alive(tmp_path, monkeypatch):
    from extract_fakes import FakeOllamaHTTP

    http = FakeOllamaHTTP().install(monkeypatch)
    settings = build_env(tmp_path)
    prompt = load_frozen(settings.extract.prompt_file, settings.extract.prompt_sha256, "extraction prompt")
    w = WindowText(1, 30.0, 60.0, TEXTS[1])
    messages, fmt, num_predict = extract_stage.window_request(settings, prompt, w)
    OllamaModelClient(settings, keep_alive=settings.extract.stage.keep_alive).chat(
        "gemma4:e4b", messages, fmt, settings.extract.num_ctx, num_predict)
    ka.OllamaSessionClient(settings).chat("gemma4:e4b", messages, fmt, settings.extract.num_ctx, num_predict,
                                          keep_alive=600, truncate=settings.extract.truncate)
    stage_body, session_body = http.chat_bodies
    assert stage_body["keep_alive"] == 0 and session_body["keep_alive"] == 600
    assert {**stage_body, "keep_alive": None} == {**session_body, "keep_alive": None}


def test_the_synthetic_body_has_exactly_the_adr0049_keys(tmp_path, monkeypatch):
    from extract_fakes import FakeOllamaHTTP

    http = FakeOllamaHTTP().install(monkeypatch)
    http.chat_error = lambda body: http.httpx.Response(200, json={"message": {"content": "{}"}, "done_reason": "stop"})
    settings = build_env(tmp_path)
    body = case_body([18])
    o = body["options"]
    ka.OllamaSessionClient(settings).chat(body["model"], body["messages"], body["format"], o["num_ctx"],
                                          o["num_predict"], keep_alive=0, truncate=None,
                                          temperature=o["temperature"], seed=o["seed"])
    (sent,) = http.chat_bodies
    assert sent == {**body, "keep_alive": 0}  # determinism.py's body: no truncate field


def test_evidence_files_hold_hashes_and_counts_and_replies_go_to_replies_jsonl(tmp_path):
    _result, _fake, settings, _ = session(tmp_path)
    folder = out_folder(settings)
    assert sorted(p.name for p in folder.iterdir()) == ["replies.jsonl", "session.json", "windows.json"]
    for name in ("session.json", "windows.json"):
        text = (folder / name).read_text(encoding="utf-8")
        assert "concept 0" not in text and TEXTS[0] not in text and "synthetic [18]" not in text
    lines = [json.loads(line) for line in (folder / "replies.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 20 and {(x["part"], x["attempt"]) for x in lines} == {("day4", 1), ("synthetic", 1)}
    assert lines[0]["content"] == reply(record(0))


def test_nothing_is_written_into_the_workspace(tmp_path):
    settings = build_env(tmp_path)
    ws = settings.jobs.workspaces_dir / DAY4
    before = tree(ws)
    ka.run_session(settings, FakeOllama(), DAY4, lambda p: contextlib.nullcontext(), Vram(FakeOllama()),
                   now=lambda: NOW)
    assert tree(ws) == before


# -- comparisons ---------------------------------------------------------------------------------------------------


def test_a_changed_day4_reply_in_a_repeat_fails_the_rule(tmp_path):
    fake = FakeOllama()
    changed = record(1, concepts=[{"label": "concept 1", "aliases": []}])
    fake.change[(3, "day4", 1)] = reply(changed) + " "  # same record, different bytes, in the reversed repeat
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "fail"
    (d,) = result["differences"]
    assert (d["run"], d["item"], d["raw_equal"], d["parsed_equal"]) == ("day4_repeat_3", 1, False, True)


def test_a_changed_parsed_record_counts_even_if_still_valid(tmp_path):
    fake = FakeOllama()
    fake.change[(1, "day4", 2)] = reply(record(2, important=True, cue="remember this"))
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "fail"
    assert result["differences"][0]["parsed_equal"] is False


def test_a_changed_synthetic_reply_fails_even_when_day4_is_identical(tmp_path):
    fake = FakeOllama()
    fake.change[(3, "synthetic", "k3")] = json.dumps({"windows": [{"window_index": 21}]})
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "fail"
    (d,) = result["differences"]
    assert (d["run"], d["part"], d["item"]) == ("synthetic_repeat_3", "synthetic", "k3")


def test_an_invalid_repeat_reply_is_a_difference(tmp_path):
    fake = FakeOllama()
    fake.change[(2, "day4", 0)] = "not json"
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "fail"
    assert result["differences"][0]["category"] == "not_json"


# -- references ----------------------------------------------------------------------------------------------------


def test_run0_not_matching_v2_stops_before_any_repeat(tmp_path):
    fake = FakeOllama()
    fake.change[(0, "day4", 1)] = reply(record(1, concepts=[{"label": "other", "aliases": []}]))
    result, fake, *_ = session(tmp_path, fake)
    assert result["outcome"] == "stopped_reference"
    assert result["reference_failure"] == {"reference": "day4_run0", "not_valid_on_attempt_1": [],
                                           "records_not_equal_to_v2": [1]}
    assert [r["run"] for r in result["runs"]] == ["run0"]
    assert all(c["keep_alive"] == 0 for c in fake.calls)


def test_synthetic_reference_not_reproduced_stops_before_any_repeat(tmp_path):
    fake = FakeOllama()
    fake.change[(0, "synthetic", "k3")] = json.dumps({"windows": []})
    result, fake, *_ = session(tmp_path, fake)
    assert result["outcome"] == "stopped_reference"
    assert result["reference_failure"] == {"reference": "adr0049_case", "hash_not_reproduced": ["k3"]}
    assert all(c["keep_alive"] == 0 for c in fake.calls)


# -- void sessions -------------------------------------------------------------------------------------------------


def test_another_model_appearing_voids_the_session(tmp_path):
    fake = FakeOllama()
    fake.extra_model_after = 6  # during Day 4 repeat 1
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "void"
    assert result["void_cause"]["check"] == "resident_only_gemma"
    assert result["void_cause"]["before"] == "day4_repeat_2"


def test_a_reload_inside_the_session_voids_it(tmp_path):
    fake = FakeOllama()
    fake.force_load_at = 9  # the second call of Day 4 repeat 2
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "void"
    assert result["void_cause"]["check"] == "no_load_in_session"


def test_a_reference_call_without_a_load_voids_the_session(tmp_path):
    fake = FakeOllama()
    fake.resident_models = []
    orig = fake.chat

    def chat(*a, **kw):
        content, m = orig(*a, **kw)
        if len(fake.calls) == 2:
            m["load_duration_s"] = 0.02
        return content, m

    fake.chat = chat
    result, *_ = session(tmp_path, fake)
    assert result["outcome"] == "void"
    assert result["void_cause"]["check"] == "load_per_call"


def test_idle_vram_dropping_voids_the_session(tmp_path):
    settings = build_env(tmp_path)
    fake = FakeOllama()
    vram = Vram(fake)
    orig = fake.chat

    def chat(*a, **kw):
        out = orig(*a, **kw)
        if len(fake.calls) == 9:  # in Day 4 repeat 2, after repeat 1's idle reference was taken
            vram.drop = True
        return out

    fake.chat = chat
    result = ka.run_session(settings, fake, DAY4, lambda p: contextlib.nullcontext(), vram, now=lambda: NOW)
    assert result["outcome"] == "void"
    assert result["void_cause"]["check"] == "idle_vram_above_baseline"


def test_an_expiring_model_voids_the_session(tmp_path):
    settings = build_env(tmp_path)
    fake = FakeOllama()
    later = NOW + timedelta(minutes=30)
    result = ka.run_session(settings, fake, DAY4, lambda p: contextlib.nullcontext(), Vram(fake),
                            now=lambda: later)
    assert result["outcome"] == "void" and result["void_cause"]["check"] == "resident_not_expiring"


def test_an_ollama_error_voids_the_session_and_records_its_cause(tmp_path):
    fake = FakeOllama()
    fake.fail_on = (2, "day4", 1)
    result, fake, settings, _ = session(tmp_path, fake)
    assert result["outcome"] == "void"
    assert result["void_cause"] == {"check": "ollama_error", "run": "day4_repeat_2", "part": "day4", "item": 1,
                                    "error": "OllamaError"}
    saved = json.loads((out_folder(settings) / "session.json").read_text(encoding="utf-8"))
    assert saved["void_cause"]["check"] == "ollama_error" and saved["outcome"] == "void"
    assert fake.unloads[-1] == "gemma4:e4b"


def test_a_difference_before_a_void_check_counts_as_failure(tmp_path):
    fake = FakeOllama()
    fake.change[(1, "day4", 0)] = reply(record(0)) + "\n"  # Day 4 repeat 1 differs ...
    fake.extra_model_after = 7  # ... then another model appears: the session is void, the difference stands
    result, *_ = session(tmp_path, fake)
    assert result["void_cause"]["check"] == "resident_only_gemma"
    assert result["outcome"] == "fail"
    assert len(result["differences"]) == 1


def test_a_session_folder_without_a_recorded_cause_blocks_the_next_session(tmp_path):
    settings = build_env(tmp_path)
    old = settings.extract.keepalive.out_dir / "20261122T100000Z"
    old.mkdir(parents=True)
    (old / "replies.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ka.KeepaliveRefused, match="cause.md"):
        ka.run_session(settings, FakeOllama(), DAY4, lambda p: contextlib.nullcontext(), lambda: 1000)
    (old / "cause.md").write_text("worker killed by hand\n", encoding="utf-8")
    fake = FakeOllama()
    assert ka.run_session(settings, fake, DAY4, lambda p: contextlib.nullcontext(), Vram(fake),
                          now=lambda: NOW)["outcome"] == "pass"


# -- refusals ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("lecture", ["yt-5vqk6HnITko", "yt-B7TQYJLfYZQ", "sha256-" + "e" * 32])
def test_any_lecture_but_day4_is_refused_before_any_call(tmp_path, lecture):
    settings = build_env(tmp_path)
    fake = FakeOllama()
    with pytest.raises(ka.KeepaliveRefused):
        ka.run_session(settings, fake, lecture, lambda p: contextlib.nullcontext(), lambda: 1000)
    assert fake.calls == [] and not settings.extract.keepalive.out_dir.exists()


def test_the_held_out_lecture_is_refused_by_name(tmp_path):
    settings = build_env(tmp_path)
    with pytest.raises(ka.KeepaliveRefused, match="held-out"):
        ka.load_inputs(settings, "yt-5vqk6HnITko")


def test_a_synthetic_case_file_other_than_the_frozen_one_is_refused(tmp_path):
    settings = build_env(tmp_path)
    case_file = settings.extract.keepalive.synthetic_case_file
    case_file.write_text(case_file.read_text(encoding="utf-8").replace("placeholder", "other"), encoding="utf-8")
    fake = FakeOllama()
    with pytest.raises(ka.KeepaliveRefused, match="sha256"):
        ka.run_session(settings, fake, DAY4, lambda p: contextlib.nullcontext(), lambda: 1000)
    assert fake.calls == []


def test_another_served_digest_is_refused_before_any_call(tmp_path):
    settings = build_env(tmp_path)
    fake = FakeOllama()
    fake.digest = lambda model: "0" * 64
    with pytest.raises(ka.KeepaliveRefused, match="frozen"):
        ka.run_session(settings, fake, DAY4, lambda p: contextlib.nullcontext(), lambda: 1000)
    assert fake.calls == [] and not settings.extract.keepalive.out_dir.exists()


def test_the_configured_case_file_is_the_committed_frozen_one():
    settings = load_settings()
    k = settings.extract.keepalive
    assert hashlib.sha256(k.synthetic_case_file.read_bytes()).hexdigest() == k.synthetic_case_sha256
    cases, _ = ka.load_cases(settings)
    assert [c.reference_sha256[:8] for c in cases] == ["1d414909", "e2a7020f"]
    assert k.lecture_id == DAY4 and k.keep_alive == 600 and k.reference_extract_key == REF_KEY
