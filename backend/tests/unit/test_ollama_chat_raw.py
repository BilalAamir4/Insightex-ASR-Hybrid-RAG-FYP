"""chat_raw / chat_json (ADR-0002 call contract) against a fake HTTP client: nothing is sent to Ollama."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from insightex.llm import ollama_client as oc


class FakeHttp:
    def __init__(self, reply: dict):
        self.reply, self.posts = reply, []

    def __call__(self, timeout=None):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return FakeResponse({"models": [{"name": "qwen3.5:latest"}]})

    def post(self, url, json=None):
        self.posts.append(json)
        return FakeResponse(self.reply)


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def reply(content: str, done_reason: str = "stop") -> dict:
    return {"message": {"content": content}, "done_reason": done_reason, "prompt_eval_count": 12, "eval_count": 4,
            "eval_duration": 2_000_000_000, "total_duration": 3_000_000_000, "load_duration": 0}


@pytest.fixture
def http(monkeypatch):
    def install(data):
        fake = FakeHttp(data)
        monkeypatch.setattr(oc.httpx, "Client", fake)
        return fake

    return install


MSGS = [{"role": "user", "content": "hi"}]
FMT = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


def test_chat_raw_sends_the_format_dict_and_returns_unparsed_content(http):
    fake = http(reply('{"a": 1}'))
    content, m = oc.chat_raw(MSGS, FMT, num_ctx=2048, num_predict=64)
    assert content == '{"a": 1}' and m.tokens_per_sec == 2.0 and m.num_ctx == 2048
    body = fake.posts[0]
    assert body["format"] == FMT and body["think"] is False and body["options"]["num_ctx"] == 2048
    assert body["options"]["num_predict"] == 64 and body["options"]["temperature"] == 0


def test_chat_raw_budget_rule_refuses_before_sending(http):
    fake = http(reply("{}"))
    with pytest.raises(oc.PromptBudgetError):
        oc.chat_raw(MSGS, FMT, num_ctx=64, num_predict=64)
    assert fake.posts == []


def test_chat_raw_truncation_raises(http):
    http(reply('{"a": ', done_reason="length"))
    with pytest.raises(oc.OutputTruncated):
        oc.chat_raw(MSGS, FMT, num_ctx=2048, num_predict=4)


def test_chat_json_still_validates_through_chat_raw(http):
    class A(BaseModel):
        a: int

    fake = http(reply(json.dumps({"a": 5})))
    obj, _ = oc.chat_json(MSGS, A, num_ctx=2048, num_predict=64)
    assert obj.a == 5 and fake.posts[0]["format"] == A.model_json_schema()
