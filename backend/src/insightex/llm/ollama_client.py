"""Ollama call contract: one structured-output chat call plus unload.

`num_ctx` is required on every call so no caller silently inherits Ollama's
VRAM-based default context. The response is validated with pydantic.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel

MODEL = "qwen3.5:latest"

T = TypeVar("T", bound=BaseModel)


class OllamaError(RuntimeError):
    pass


class ModelMissingError(OllamaError):
    pass


@dataclass(frozen=True)
class ChatMetrics:
    prompt_eval_count: int
    eval_count: int
    eval_duration_s: float
    tokens_per_sec: float
    total_duration_s: float
    load_duration_s: float
    done_reason: str | None
    num_ctx: int

    @property
    def prompt_near_ctx_limit(self) -> bool:
        """Ollama truncates an over-long prompt silently; a count at the limit is suspect."""
        return self.prompt_eval_count >= int(self.num_ctx * 0.98)


_checked_models: set[tuple[str, str]] = set()


def _base_url() -> str:
    url = os.environ.get("OLLAMA_BASE_URL")
    if not url:
        raise OllamaError("OLLAMA_BASE_URL is not set (source env/insightex_env.sh)")
    return url.rstrip("/")


def _ensure_model(client: httpx.Client, base: str, model: str) -> None:
    if (base, model) in _checked_models:
        return
    try:
        r = client.get(f"{base}/api/tags")
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise OllamaError(f"Cannot reach Ollama at {base}: {e}") from e
    names = [m.get("name") for m in r.json().get("models", [])]
    if model not in names:
        raise ModelMissingError(f"Model {model!r} not found in Ollama at {base}; available: {names}")
    _checked_models.add((base, model))


def chat_json(
    messages: list[dict],
    schema: type[T],
    num_ctx: int,
    keep_alive: str | int = "10m",
    temperature: float = 0,
    seed: int = 42,
    num_predict: int | None = None,
    timeout: float = 600.0,
    model: str = MODEL,
) -> tuple[T, ChatMetrics]:
    """POST /api/chat with a JSON Schema `format`; return (validated object, metrics).

    `schema` is a pydantic model class; its JSON Schema is sent as `format` and the
    reply is validated against it. Raises OllamaError / ModelMissingError /
    pydantic.ValidationError.
    """
    base = _base_url()
    options: dict = {"num_ctx": num_ctx, "temperature": temperature, "seed": seed}
    if num_predict is not None:
        options["num_predict"] = num_predict
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": schema.model_json_schema(),
        "keep_alive": keep_alive,
        "options": options,
    }
    with httpx.Client(timeout=timeout) as client:
        _ensure_model(client, base, model)
        try:
            r = client.post(f"{base}/api/chat", json=body)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaError(f"/api/chat failed: {e}") from e
    data = r.json()
    msg = data.get("message", {})
    if msg.get("thinking"):
        raise OllamaError("model returned thinking text although think=false")
    parsed = schema.model_validate_json(msg.get("content", ""))
    eval_s = data.get("eval_duration", 0) / 1e9
    eval_n = data.get("eval_count", 0)
    metrics = ChatMetrics(
        prompt_eval_count=data.get("prompt_eval_count", 0),
        eval_count=eval_n,
        eval_duration_s=eval_s,
        tokens_per_sec=eval_n / eval_s if eval_s else 0.0,
        total_duration_s=data.get("total_duration", 0) / 1e9,
        load_duration_s=data.get("load_duration", 0) / 1e9,
        done_reason=data.get("done_reason"),
        num_ctx=num_ctx,
    )
    return parsed, metrics


def loaded_models() -> list[dict]:
    """Entries from /api/ps (empty list when nothing is resident)."""
    r = httpx.get(f"{_base_url()}/api/ps", timeout=10)
    r.raise_for_status()
    return r.json().get("models", [])


def unload(model: str = MODEL, wait_s: float = 30.0) -> bool:
    """Send keep_alive=0 and poll /api/ps until the model is gone. True if it unloaded."""
    base = _base_url()
    r = httpx.post(f"{base}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    r.raise_for_status()
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if not any(m.get("name") == model for m in loaded_models()):
            return True
        time.sleep(0.5)
    return False
