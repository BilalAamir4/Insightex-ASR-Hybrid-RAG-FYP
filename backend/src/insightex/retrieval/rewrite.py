"""The ADR-0046 question rewrite: build the gated request, check the reply, fall back on any problem.

Every byte of the request is fixed by ADR-0046 and the G5 run: `build_body` produces the body the G5 harness
(`tools/eval_retrieval/g5_rewrite.py`) sent, and `parse_response` applies the same usability checks. Tests compare both
against the harness and against the 47 recorded responses. The question and the rewrite are never logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from insightex.core.config import Settings
from insightex.jobs.gpu_lease import FileGpuLease, GpuBusy
from insightex.llm import ollama_client

log = logging.getLogger(__name__)

# ADR-0046's output schema, literally (key order included: the body is compared byte for byte).
SCHEMA: dict[str, Any] = {"type": "object", "properties": {"english_question": {"type": "string", "minLength": 1, "maxLength": 300}},
                          "required": ["english_question"], "additionalProperties": False}


class FallbackReason(StrEnum):
    REWRITE_DISABLED = "rewrite_disabled"
    GPU_BUSY = "gpu_busy"
    LLM_NOT_LOADED = "llm_not_loaded"
    LLM_UNREACHABLE = "llm_unreachable"
    TIMEOUT = "timeout"
    UNUSABLE = "unusable"
    ERROR = "error"


@dataclass(frozen=True)
class RewriteOutcome:
    rewrite: str | None  # None: search the original question only
    fallback_reason: FallbackReason | None
    ms: float | None  # duration of the Ollama call, when one was made


def load_prompt(settings: Settings) -> str | None:
    """The system prompt, or None (rewrite disabled) if it is switched off or the file's sha256 is not the pinned one."""
    r = settings.retrieval
    if not r.rewrite_enabled:
        return None
    try:
        raw = r.rewrite_prompt_file.read_bytes()
    except OSError:
        log.error("rewrite disabled: cannot read %s", r.rewrite_prompt_file)
        return None
    if hashlib.sha256(raw).hexdigest() != r.rewrite_prompt_sha256:
        log.error("rewrite disabled: %s does not have the sha256 pinned in retrieval.rewrite_prompt_sha256 (ADR-0046)",
                  r.rewrite_prompt_file.name)
        return None
    return raw.decode("utf-8").rstrip("\n")


def _options(settings: Settings) -> dict[str, Any]:
    return {"num_ctx": settings.ollama.num_ctx, "temperature": 0, "seed": settings.ollama.seed,
            "num_predict": settings.retrieval.rewrite_num_predict}


def build_body(settings: Settings, system: str, question: str) -> dict[str, Any]:
    """The rewrite request body of ADR-0046, key for key as the G5 harness built it."""
    return {"model": settings.ollama.model, "stream": False, "think": False, "format": SCHEMA,
            "keep_alive": settings.ollama.keep_alive,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
            "options": _options(settings)}


def build_warmup_body(settings: Settings) -> dict[str, Any]:
    """A chat request with no messages: Ollama loads the model and answers at once. Model, keep_alive and options are
    the rewrite request's, so the runner it starts is the one the first rewrite uses (no reload)."""
    return {"model": settings.ollama.model, "stream": False, "think": False, "keep_alive": settings.ollama.keep_alive,
            "messages": [], "options": _options(settings)}


def parse_response(data: dict[str, Any]) -> tuple[str | None, list[str]]:
    """(rewrite, problems). The rewrite is usable only when `problems` is empty (ADR-0046's unusable-output rules)."""
    msg = data.get("message", {})
    content, thinking = msg.get("content", ""), msg.get("thinking") or ""
    problems: list[str] = []
    rewrite = None
    if data.get("done_reason") != "stop":
        problems.append(f"done_reason={data.get('done_reason')}")
    if "<think>" in content + thinking or "</think>" in content + thinking or thinking:
        problems.append("think text in the response")
    try:
        obj = json.loads(content)
        if not isinstance(obj, dict) or "english_question" not in obj:
            raise ValueError
        rewrite = obj["english_question"]
        if set(obj) != {"english_question"} or not isinstance(rewrite, str):
            problems.append("does not match the schema")
        elif not rewrite.strip():
            problems.append("empty rewrite")
        elif "\n" in rewrite:
            problems.append("newline in the rewrite")
        elif len(rewrite) > 300:
            problems.append("longer than 300 characters")
    except (ValueError, TypeError):
        problems.append("not valid JSON for the schema")
    return rewrite, problems


def model_loaded(settings: Settings, entries: list[dict]) -> bool:
    """True if the configured model is resident in Ollama with the configured context (else a call would reload it)."""
    return any(e.get("name") == settings.ollama.model and e.get("context_length") in (None, settings.ollama.num_ctx) for e in entries)


def shared_lease(settings: Settings):
    """The GPU lease for a Q&A call: shared, taken without waiting; no lease when `gpu.lease_enabled` is false."""
    if not settings.gpu.lease_enabled:
        return nullcontext()
    return FileGpuLease(settings).shared("ask-rewrite", timeout_s=0)


def rewrite_question(settings: Settings, system: str | None, question: str, *, lease=shared_lease,
                     post=ollama_client.post_chat, loaded=ollama_client.loaded_models) -> RewriteOutcome:
    """Rewrite `question` into English, or say why not. Never raises; the caller then searches the original alone."""
    if system is None:
        return RewriteOutcome(None, FallbackReason.REWRITE_DISABLED, None)
    try:
        with lease(settings):
            try:
                entries = loaded(settings.ollama)
            except (httpx.HTTPError, ValueError):  # /api/ps unreachable or unreadable: as an unreachable model server
                return RewriteOutcome(None, FallbackReason.LLM_UNREACHABLE, None)
            if not model_loaded(settings, entries):
                return RewriteOutcome(None, FallbackReason.LLM_NOT_LOADED, None)
            timeout = settings.retrieval.rewrite_timeout_s
            t0 = time.perf_counter()
            try:
                data = post(build_body(settings, system, question), timeout=timeout, ollama=settings.ollama)
            except ollama_client.OllamaTimeout:
                return RewriteOutcome(None, FallbackReason.TIMEOUT, (time.perf_counter() - t0) * 1000)
            except ollama_client.OllamaUnreachable:
                return RewriteOutcome(None, FallbackReason.LLM_UNREACHABLE, (time.perf_counter() - t0) * 1000)
            except ollama_client.OllamaError:
                return RewriteOutcome(None, FallbackReason.ERROR, (time.perf_counter() - t0) * 1000)
            elapsed = time.perf_counter() - t0
    except GpuBusy:
        return RewriteOutcome(None, FallbackReason.GPU_BUSY, None)
    ms = elapsed * 1000
    if elapsed > timeout:  # G5 counted any call over the timeout as a timeout, even one that finished
        return RewriteOutcome(None, FallbackReason.TIMEOUT, ms)
    rewrite, problems = parse_response(data)
    if problems:
        return RewriteOutcome(None, FallbackReason.UNUSABLE, ms)
    return RewriteOutcome(rewrite, None, ms)


def warm_up(settings: Settings, *, lease=shared_lease, post=ollama_client.post_chat) -> tuple[str, str | None]:
    """Ask Ollama to load the rewrite model. Returns (result, reason): ("loaded", None), or ("skipped", why)."""
    if not settings.retrieval.rewrite_enabled:
        return "skipped", FallbackReason.REWRITE_DISABLED
    try:
        with lease(settings):
            try:
                post(build_warmup_body(settings), timeout=settings.ollama.request_timeout_s, ollama=settings.ollama)
            except ollama_client.OllamaUnreachable:
                return "skipped", FallbackReason.LLM_UNREACHABLE
            except ollama_client.OllamaError:
                return "skipped", FallbackReason.ERROR
    except GpuBusy:
        return "skipped", FallbackReason.GPU_BUSY
    return "loaded", None
