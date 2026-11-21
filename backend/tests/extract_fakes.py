"""Test doubles for the `extract` stage (ADR-0054): a model client with no Ollama behind it.

`FakeExtractClient` serves the frozen version and digest, refuses the self-test probe like Ollama 0.40.2 with
truncate false, and answers each window call with a valid record (one concept named after the window) unless a test
sets `respond`. Every call is recorded.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from insightex.extract.calls import SELF_TEST_FORMAT
from insightex.llm.ollama_client import PromptTooLong

FROZEN_VERSION = "0.40.2"
FROZEN_DIGEST = "dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c"


def target_of(fmt: dict) -> int:
    """The window index a one-window extraction `format` asks for."""
    return fmt["properties"]["windows"]["items"]["properties"]["window_index"]["enum"][0]


def record(i: int, **kw: Any) -> dict[str, Any]:
    base = {"window_index": i, "concepts": [{"label": f"concept {i}", "aliases": []}], "relations": [],
            "important": False, "cue": None, "is_recap": False}
    return {**base, **kw}


def reply(*records: dict[str, Any]) -> str:
    return json.dumps({"windows": list(records)})


def metrics(prompt_eval_count: int = 900, eval_count: int = 60) -> dict[str, Any]:
    return {"prompt_eval_count": prompt_eval_count, "eval_count": eval_count, "eval_duration_s": 1.0,
            "tokens_per_sec": float(eval_count), "total_duration_s": 2.0, "load_duration_s": 0.5,
            "done_reason": "stop", "num_ctx": 8192}


class FakeExtractClient:
    def __init__(self) -> None:
        self.served_version = FROZEN_VERSION
        self.served_digest = FROZEN_DIGEST
        self.refuse_probe = True
        self.resident_models: list[dict[str, Any]] = []
        # (window_index, attempt number, messages) -> (content, metrics), or raise; None = a valid record
        self.respond: Callable[[int, int, list[dict]], tuple[str, dict[str, Any]]] | None = None
        self.chats: list[dict[str, Any]] = []  # window calls only
        self.probes = 0
        self.unloaded: list[str] = []
        self.order: list[str] = []  # resident, unload:<model>, version, digest, self_test, chat:<i>

    def digest(self, model: str) -> str:
        self.order.append("digest")
        return self.served_digest

    def version(self) -> str:
        self.order.append("version")
        return self.served_version

    def resident(self) -> list[dict[str, Any]]:
        self.order.append("resident")
        return list(self.resident_models)

    def unload(self, model: str) -> bool:
        self.order.append(f"unload:{model}")
        self.unloaded.append(model)
        return True

    def chat(self, model: str, messages: list[dict], format_schema: dict, num_ctx: int,
             num_predict: int) -> tuple[str, dict[str, Any]]:
        if format_schema == SELF_TEST_FORMAT:
            self.order.append("self_test")
            self.probes += 1
            if self.refuse_probe:
                raise PromptTooLong(9000, num_ctx, "the input length exceeds the context length")
            return "true", metrics(prompt_eval_count=num_ctx)
        i = target_of(format_schema)
        attempt = 1 + sum(1 for c in self.chats if c["window_index"] == i)
        self.order.append(f"chat:{i}")
        self.chats.append({"window_index": i, "attempt": attempt, "messages": messages, "format": format_schema,
                           "num_ctx": num_ctx, "num_predict": num_predict, "model": model})
        if self.respond is not None:
            return self.respond(i, attempt, messages)
        return reply(record(i)), metrics()


# -- a fake Ollama HTTP server (httpx.MockTransport), for tests that use the real OllamaModelClient -----------------


class FakeOllamaHTTP:
    """Answers /api/tags, /api/version, /api/ps, /api/generate (unload) and /api/chat like Ollama 0.40.2 with
    `truncate: false`: the self-test probe (format {"type": "boolean"}) gets the 400 exceed_context_size_error, every
    other chat a valid one-window record. `chat_error(body)` may return an httpx.Response or raise an httpx error to
    simulate a failure; `models` lists the tags Ollama serves. Every /api/chat body is kept in `chat_bodies`."""

    def __init__(self) -> None:
        import httpx

        self.httpx = httpx
        self.version = FROZEN_VERSION
        self.models: dict[str, str] = {"gemma4:e4b": FROZEN_DIGEST}
        self.resident: list[str] = []
        self.chat_bodies: list[dict[str, Any]] = []
        self.unloads: list[str] = []
        self.chat_error: Callable[[dict], Any] | None = None

    def handler(self, request):
        httpx = self.httpx
        path = request.url.path
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n, "digest": d} for n, d in self.models.items()]})
        if path == "/api/version":
            return httpx.Response(200, json={"version": self.version})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": n} for n in self.resident]})
        body = json.loads(request.content or b"{}")
        if path == "/api/generate":
            self.unloads.append(body.get("model"))
            self.resident = [n for n in self.resident if n != body.get("model")]
            return httpx.Response(200, json={"done": True})
        if path == "/api/chat":
            if body.get("format") == SELF_TEST_FORMAT:
                err = {"type": "exceed_context_size_error", "n_prompt_tokens": 3100,
                       "n_ctx": body["options"]["num_ctx"], "message": "the request exceeds the context size"}
                return httpx.Response(400, json={"error": json.dumps({"error": err})})
            self.chat_bodies.append(body)
            if self.chat_error is not None:
                failure = self.chat_error(body)
                if failure is not None:
                    return failure
            i = target_of(body["format"])
            return httpx.Response(200, json={"message": {"role": "assistant", "content": reply(record(i))},
                                             "done_reason": "stop", "prompt_eval_count": 900, "eval_count": 60,
                                             "eval_duration": 1_000_000_000, "total_duration": 2_000_000_000,
                                             "load_duration": 500_000_000})
        return httpx.Response(404, json={"error": f"no route {path}"})

    def install(self, monkeypatch) -> FakeOllamaHTTP:
        """Route every httpx call (Client, get, post) through this fake for the rest of the test."""
        httpx = self.httpx
        transport = httpx.MockTransport(self.handler)
        real_client = httpx.Client

        def client(*args, **kw):
            kw.pop("transport", None)
            return real_client(*args, transport=transport, **kw)

        def get(url, **kw):
            with client(timeout=kw.pop("timeout", None)) as c:
                return c.get(url, **kw)

        def post(url, **kw):
            with client(timeout=kw.pop("timeout", None)) as c:
                return c.post(url, **kw)

        monkeypatch.setattr(httpx, "Client", client)
        monkeypatch.setattr(httpx, "get", get)
        monkeypatch.setattr(httpx, "post", post)
        from insightex.llm import ollama_client

        monkeypatch.setattr(ollama_client, "_checked_models", set())  # the model check runs again in each test
        return self
