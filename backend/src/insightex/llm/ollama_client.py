"""Ollama call contract: one structured-output chat call plus unload.

`num_ctx` is required on every call so no caller silently inherits Ollama's
VRAM-based default context (callers pass settings.ollama.num_ctx); `num_predict` defaults to
settings.ollama.num_predict. All other values come from the `ollama:` config section; library code
takes an OllamaSettings argument and falls back to get_settings() only when none is passed.
Budget rule: estimated prompt tokens + num_predict must fit in num_ctx, else the call
fails before it is sent. A reply cut off at num_predict (done_reason "length") is an
error (OutputTruncated); truncated JSON is never parsed. The response is validated
with pydantic.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel

from insightex.core.config import Ollama as OllamaSettings
from insightex.core.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OllamaError(RuntimeError):
    pass


class ModelMissingError(OllamaError):
    pass


class PromptBudgetError(OllamaError):
    """Estimated prompt tokens + num_predict would not fit in num_ctx."""

    def __init__(self, estimated_prompt_tokens: int, num_predict: int, num_ctx: int):
        self.estimated_prompt_tokens, self.num_predict, self.num_ctx = estimated_prompt_tokens, num_predict, num_ctx
        super().__init__(
            f"prompt budget exceeded: ~{estimated_prompt_tokens} estimated prompt tokens + num_predict {num_predict} "
            f"= {estimated_prompt_tokens + num_predict} > num_ctx {num_ctx}"
        )


class OutputTruncated(OllamaError):
    """The reply hit num_predict (done_reason == "length"); its JSON is incomplete and was not parsed."""

    def __init__(self, eval_count: int, num_predict: int):
        self.eval_count, self.num_predict = eval_count, num_predict
        super().__init__(
            f"output truncated: done_reason=length after eval_count={eval_count} tokens (num_predict={num_predict}); "
            "raise num_predict or ask for less output"
        )


# Rough, deliberately conservative token estimate (over-estimates). Not calibrated: the real
# prompt_eval_count is logged after every call so these ratios can be tuned later.
CHARS_PER_TOKEN_LATIN = 3.5   # English prose measured around 4+ chars/token with this tokenizer family
CHARS_PER_TOKEN_ARABIC = 1.5  # Urdu/Arabic script is much more expensive per character
PER_MESSAGE_OVERHEAD_TOKENS = 8


def _is_arabic_script(ch: str) -> bool:
    o = ord(ch)
    return 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def estimate_prompt_tokens(messages: list[dict]) -> int:
    total = 0.0
    for m in messages:
        text = m.get("content", "")
        arabic = sum(1 for ch in text if _is_arabic_script(ch))
        total += arabic / CHARS_PER_TOKEN_ARABIC + (len(text) - arabic) / CHARS_PER_TOKEN_LATIN + PER_MESSAGE_OVERHEAD_TOKENS
    return int(total) + 1


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


def _cfg(ollama: OllamaSettings | None) -> OllamaSettings:
    return ollama or get_settings().ollama  # fallback when the caller passed no settings


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


def chat_json[T: BaseModel](
    messages: list[dict],
    schema: type[T],
    num_ctx: int,
    ollama: OllamaSettings | None = None,
    keep_alive: str | int | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    num_predict: int | None = None,
    timeout: float | None = None,
    model: str | None = None,
) -> tuple[T, ChatMetrics]:
    """POST /api/chat with a JSON Schema `format`; return (validated object, metrics).

    `schema` is a pydantic model class; its JSON Schema is sent as `format` and the
    reply is validated against it. Raises PromptBudgetError (before sending),
    OutputTruncated, ModelMissingError / OllamaError, or pydantic.ValidationError.
    """
    cfg = _cfg(ollama)
    keep_alive = cfg.keep_alive if keep_alive is None else keep_alive
    temperature = cfg.temperature if temperature is None else temperature
    seed = cfg.seed if seed is None else seed
    num_predict = cfg.num_predict if num_predict is None else num_predict
    timeout = cfg.request_timeout_s if timeout is None else timeout
    model = model or cfg.model
    estimated = estimate_prompt_tokens(messages)
    if estimated + num_predict > num_ctx:
        raise PromptBudgetError(estimated, num_predict, num_ctx)
    base = cfg.base_url.rstrip("/")
    options: dict = {"num_ctx": num_ctx, "temperature": temperature, "seed": seed, "num_predict": num_predict}
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": cfg.think,
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
    if msg.get("thinking") and not cfg.think:
        raise OllamaError("model returned thinking text although think=false")
    prompt_n = data.get("prompt_eval_count", 0)
    log.info("ollama chat: estimated_prompt_tokens=%d prompt_eval_count=%d eval_count=%d num_predict=%d num_ctx=%d done_reason=%s",
             estimated, prompt_n, data.get("eval_count", 0), num_predict, num_ctx, data.get("done_reason"))
    if data.get("done_reason") == "length":
        raise OutputTruncated(data.get("eval_count", 0), num_predict)
    parsed = schema.model_validate_json(msg.get("content", ""))
    eval_s = data.get("eval_duration", 0) / 1e9
    eval_n = data.get("eval_count", 0)
    metrics = ChatMetrics(
        prompt_eval_count=prompt_n,
        eval_count=eval_n,
        eval_duration_s=eval_s,
        tokens_per_sec=eval_n / eval_s if eval_s else 0.0,
        total_duration_s=data.get("total_duration", 0) / 1e9,
        load_duration_s=data.get("load_duration", 0) / 1e9,
        done_reason=data.get("done_reason"),
        num_ctx=num_ctx,
    )
    return parsed, metrics


def loaded_models(ollama: OllamaSettings | None = None) -> list[dict]:
    """Entries from /api/ps (empty list when nothing is resident)."""
    cfg = _cfg(ollama)
    r = httpx.get(f"{cfg.base_url.rstrip('/')}/api/ps", timeout=cfg.ps_timeout_s)
    r.raise_for_status()
    return r.json().get("models", [])


def unload(
    ollama: OllamaSettings | None = None,
    model: str | None = None,
    *,
    poll_interval_s: float,
    timeout_s: float,
) -> bool:
    """Send keep_alive=0 and poll /api/ps every `poll_interval_s` for up to `timeout_s`. True if it unloaded."""
    cfg = _cfg(ollama)
    model = model or cfg.model
    base = cfg.base_url.rstrip("/")
    r = httpx.post(f"{base}/api/generate", json={"model": model, "keep_alive": 0}, timeout=cfg.unload_timeout_s)
    r.raise_for_status()
    deadline = time.monotonic() + timeout_s
    while True:
        if not any(m.get("name") == model for m in loaded_models(cfg)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def _selftest() -> dict:
    """Tiny schema-valid call; reports where the model is resident. Used by tools/verify_env.py."""

    class _Probe(BaseModel):
        answer: str
        number: int

    msgs = [{"role": "user", "content": "Is 7 prime? Reply as JSON: answer (string) and number (the integer 7)."}]
    obj, m = chat_json(msgs, _Probe, num_ctx=4096, num_predict=100)

    # Truncation path: a 3-token cap cannot hold the JSON, so this must raise and never parse.
    try:
        chat_json(msgs, _Probe, num_ctx=4096, num_predict=3)
    except OutputTruncated as e:
        truncation = {"raises": True, "eval_count": e.eval_count, "num_predict": e.num_predict}
    else:
        raise AssertionError("num_predict=3 did not raise OutputTruncated")

    # Budget path: fails before any request is sent.
    try:
        chat_json(msgs, _Probe, num_ctx=64, num_predict=64)
    except PromptBudgetError:
        budget_raises = True
    else:
        raise AssertionError("budget rule did not raise PromptBudgetError")
    entry = next((e for e in loaded_models() if e.get("name") == get_settings().ollama.model), None)
    size, vram = (entry or {}).get("size", 0), (entry or {}).get("size_vram", 0)
    return {
        "parsed": obj.model_dump(),
        "tokens_per_sec": round(m.tokens_per_sec, 1),
        "prompt_eval_count": m.prompt_eval_count,
        "gpu_pct": round(100 * vram / size, 1) if size else None,
        "truncation": truncation,
        "budget_raises": budget_raises,
    }


if __name__ == "__main__":
    import json
    import sys

    if "--selftest" in sys.argv:
        print(json.dumps(_selftest()))
    elif "--unload" in sys.argv:
        _s = get_settings()
        print(json.dumps({"unloaded": unload(poll_interval_s=_s.gpu.ollama_poll_interval_s, timeout_s=_s.ollama.unload_wait_s)}))
    else:
        sys.exit("usage: python -m insightex.llm.ollama_client --selftest | --unload")
