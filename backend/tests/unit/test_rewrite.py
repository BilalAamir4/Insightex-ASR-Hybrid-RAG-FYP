"""The ADR-0046 rewrite: the request is byte-identical to the one gate G5 sent, replies are judged as G5 judged them,
and every failure falls back to the original question (ADR-0047). No Ollama is needed."""

from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from insightex.core.config import load_settings
from insightex.jobs.gpu_lease import GpuBusy
from insightex.llm import ollama_client
from insightex.retrieval import rewrite as rw

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = json.loads((Path(__file__).resolve().parents[1] / "golden" / "rewrite_request_g5.json").read_text(encoding="utf-8"))
G5_EVIDENCE = ROOT / "docs" / "evidence" / "m6" / "g5_rewrites.json"


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def system(settings):
    text = rw.load_prompt(settings)
    assert text is not None
    return text


# -- the request ----------------------------------------------------------------------------------------------------


def test_prompt_file_is_the_pinned_one(settings, system):
    import hashlib

    raw = settings.retrieval.rewrite_prompt_file.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == settings.retrieval.rewrite_prompt_sha256 == GOLDEN["prompt_sha256"]
    assert system == raw.decode("utf-8").rstrip("\n")


@pytest.mark.parametrize("entry", GOLDEN["requests"], ids=lambda e: e["question"][:24])
def test_request_is_byte_identical_to_the_golden_g5_request(settings, system, entry):
    """The golden file was captured from tools/eval_retrieval/g5_rewrite.py as committed with the G5 evidence."""
    assert json.dumps(rw.build_body(settings, system, entry["question"])) == entry["wire_json"]


def test_request_is_byte_identical_to_the_g5_harness_now(settings, system):
    spec = importlib.util.spec_from_file_location("g5_rewrite_harness", ROOT / "tools" / "eval_retrieval" / "g5_rewrite.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    sent = []

    def fake_post(url, body, timeout=600):
        sent.append(json.dumps(body))
        return {"message": {"content": '{"english_question": "x"}'}, "done_reason": "stop"}, 0.1

    harness.post = fake_post
    o = settings.ollama
    for entry in GOLDEN["requests"]:
        harness.rewrite_call("http://x", o.model, system, entry["question"], o.num_ctx, settings.retrieval.rewrite_num_predict,
                             o.seed, o.keep_alive)
        assert sent[-1] == json.dumps(rw.build_body(settings, system, entry["question"]))


def test_post_chat_puts_the_golden_bytes_on_the_wire(settings, system, monkeypatch):
    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured.update(url=url, content=content, timeout=timeout)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    entry = GOLDEN["requests"][1]
    ollama_client.post_chat(rw.build_body(settings, system, entry["question"]), timeout=2.0, ollama=settings.ollama)
    assert captured["content"] == entry["wire_json"].encode("utf-8")
    assert captured["url"].endswith(GOLDEN["url_path"]) and captured["timeout"] == 2.0


def test_post_chat_maps_errors(settings, monkeypatch):
    def raiser(exc):
        def f(*a, **k):
            raise exc
        return f

    for exc, expected in ((httpx.ReadTimeout("t"), ollama_client.OllamaTimeout), (httpx.ConnectError("c"), ollama_client.OllamaUnreachable),
                          (httpx.DecodingError("d"), ollama_client.OllamaError)):
        monkeypatch.setattr(httpx, "post", raiser(exc))
        with pytest.raises(expected):
            ollama_client.post_chat({}, timeout=1, ollama=settings.ollama)


def test_warm_up_request_matches_the_rewrite_request_so_ollama_does_not_reload(settings, system):
    rewrite, warm = rw.build_body(settings, system, "q"), rw.build_warmup_body(settings)
    for key in ("model", "keep_alive", "options", "think"):
        assert warm[key] == rewrite[key]
    assert warm["messages"] == [] and warm["options"] == {"num_ctx": 8192, "temperature": 0, "seed": 42, "num_predict": 64}


# -- the reply ------------------------------------------------------------------------------------------------------


@pytest.mark.skipif(not G5_EVIDENCE.is_file(), reason="G5 evidence not present")
def test_all_47_recorded_g5_replies_are_judged_the_same_way():
    rows = json.loads(G5_EVIDENCE.read_text(encoding="utf-8"))["rewrites"]
    assert len(rows) == 47
    for row in rows:
        rewrite, problems = rw.parse_response({"message": {"content": row["raw_content"]}, "done_reason": row["done_reason"]})
        assert (rewrite, problems) == (row["rewrite"], []) and row["usable"]


@pytest.mark.parametrize("reply, problem", [
    ({"message": {"content": '{"english_question": "ok"}'}, "done_reason": "length"}, "done_reason=length"),
    ({"message": {"content": '{"english_question": "ok"}', "thinking": "hmm"}, "done_reason": "stop"}, "think text in the response"),
    ({"message": {"content": '<think>x</think>{"english_question": "ok"}'}, "done_reason": "stop"}, "think text in the response"),
    ({"message": {"content": "not json"}, "done_reason": "stop"}, "not valid JSON for the schema"),
    ({"message": {"content": '["english_question"]'}, "done_reason": "stop"}, "not valid JSON for the schema"),
    ({"message": {"content": '{"english_question": "ok", "extra": 1}'}, "done_reason": "stop"}, "does not match the schema"),
    ({"message": {"content": '{"english_question": 5}'}, "done_reason": "stop"}, "does not match the schema"),
    ({"message": {"content": '{"english_question": "  "}'}, "done_reason": "stop"}, "empty rewrite"),
    ({"message": {"content": '{"english_question": "a\\nb"}'}, "done_reason": "stop"}, "newline in the rewrite"),
    ({"message": {"content": json.dumps({"english_question": "x" * 301})}, "done_reason": "stop"}, "longer than 300 characters"),
])
def test_unusable_replies(reply, problem):
    assert problem in rw.parse_response(reply)[1]


# -- the fallbacks --------------------------------------------------------------------------------------------------


class Env:
    """Fake lease, /api/ps and /api/chat that record the order of events."""

    def __init__(self, loaded=None, reply=None, post_error=None, ps_error=None, busy=False):
        self.events: list[str] = []
        self.loaded = [{"name": "qwen3.5:latest", "context_length": 8192}] if loaded is None else loaded
        self.reply = reply or {"message": {"content": '{"english_question": "What is a server?"}'}, "done_reason": "stop"}
        self.post_error, self.ps_error, self.busy = post_error, ps_error, busy
        self.bodies: list[dict] = []

    @contextmanager
    def lease(self, settings):
        if self.busy:
            raise GpuBusy(None)
        self.events.append("lease+")
        try:
            yield
        finally:
            self.events.append("lease-")

    def ps(self, ollama):
        self.events.append("ps")
        if self.ps_error:
            raise self.ps_error
        return self.loaded

    def post(self, body, timeout, ollama):
        self.events.append("post")
        self.bodies.append(body)
        if self.post_error:
            raise self.post_error
        return self.reply

    def run(self, settings, system, question="server kya hai"):
        return rw.rewrite_question(settings, system, question, lease=self.lease, post=self.post, loaded=self.ps)


def test_success_holds_the_shared_lease_around_the_whole_call(settings, system):
    env = Env()
    out = env.run(settings, system)
    assert (out.rewrite, out.fallback_reason) == ("What is a server?", None) and out.ms is not None
    assert env.events == ["lease+", "ps", "post", "lease-"]
    assert env.bodies[0] == rw.build_body(settings, system, "server kya hai")


@pytest.mark.parametrize("env_kwargs, reason", [
    ({"busy": True}, "gpu_busy"),
    ({"loaded": []}, "llm_not_loaded"),
    ({"loaded": [{"name": "other:model", "context_length": 8192}]}, "llm_not_loaded"),
    ({"loaded": [{"name": "qwen3.5:latest", "context_length": 4096}]}, "llm_not_loaded"),
    ({"ps_error": httpx.ConnectError("down")}, "llm_unreachable"),
    ({"post_error": ollama_client.OllamaTimeout("slow")}, "timeout"),
    ({"post_error": ollama_client.OllamaUnreachable("down")}, "llm_unreachable"),
    ({"post_error": ollama_client.OllamaError("500")}, "error"),
    ({"reply": {"message": {"content": '{"english_question": "ok"}'}, "done_reason": "length"}}, "unusable"),
    ({"reply": {"message": {"content": "garbage"}, "done_reason": "stop"}}, "unusable"),
])
def test_every_failure_falls_back_with_its_reason(settings, system, env_kwargs, reason):
    out = Env(**env_kwargs).run(settings, system)
    assert out.rewrite is None and str(out.fallback_reason) == reason


def test_a_reply_that_arrives_after_the_timeout_is_a_timeout(system):
    settings = load_settings({"retrieval": {"rewrite_timeout_s": 0.0}})
    out = Env().run(settings, system)  # any real elapsed time exceeds 0 s
    assert out.rewrite is None and str(out.fallback_reason) == "timeout"


def test_busy_lease_means_the_model_is_never_asked(settings, system):
    env = Env(busy=True)
    env.run(settings, system)
    assert env.events == []


def test_disabled_rewrite_and_a_changed_prompt(tmp_path, system):
    off = load_settings({"retrieval": {"rewrite_enabled": False}})
    assert rw.load_prompt(off) is None
    assert str(Env().run(off, None).fallback_reason) == "rewrite_disabled"
    changed = tmp_path / "prompt.txt"
    changed.write_text("A different prompt.\n", encoding="utf-8")
    assert rw.load_prompt(load_settings({"retrieval": {"rewrite_prompt_file": str(changed)}})) is None  # hash no longer matches


def test_warm_up_results(settings):
    posted = []
    ok = rw.warm_up(settings, lease=Env().lease, post=lambda body, timeout, ollama: posted.append(body))
    assert ok == ("loaded", None) and posted[0]["messages"] == []
    assert rw.warm_up(settings, lease=Env(busy=True).lease, post=lambda *a, **k: 1 / 0) == ("skipped", "gpu_busy")
    down = rw.warm_up(settings, lease=Env().lease, post=Env(post_error=ollama_client.OllamaUnreachable("x")).post)
    assert down == ("skipped", "llm_unreachable")
