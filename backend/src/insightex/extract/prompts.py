"""Request building for M7 extraction and translation calls (ADR-0048, Amendment 2).

No prompt wording lives here. The instructions are the frozen files named in the `extract:` config (the extraction
prompt, the C4 context block and the C2 translation prompt), each used only when its sha256 equals the pinned value.
This module only arranges data around them:

- system message: the extraction prompt, followed by the context block when (and only when) the call carries
  context. A call without context (C4 arm B on the lecture's first window) is therefore byte-identical to arm A's;
- user message: one JSON object, `{"windows": [{"window_index", "text"}, ...]}`, plus
  `"context": [{"window_index", "precedes_window_index", "text"}, ...]` when the call has context;
- `format`: the subset of extraction schema v1 the model fills, always `{"windows": [record, ...]}` with exactly one
  record per target window, so single-window and batched arms (C3) differ only in k. The stored output is a full v1
  record built by the harness.

USER_FORMAT_VERSION and FORMAT_VERSION go into every cache key (through the request body itself).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from insightex.extract.extraction_schema import CUE_MAX, NAME_MAX, RELATION_TYPES

USER_FORMAT_VERSION = 1
FORMAT_VERSION = 1


class PromptNotFrozen(Exception):
    """A prompt file is not configured, unreadable, or does not have its pinned sha256."""


@dataclass(frozen=True)
class FrozenText:
    path: Path
    sha256: str
    text: str


def load_frozen(path: Path | None, pinned_sha256: str | None, what: str) -> FrozenText:
    if path is None or pinned_sha256 is None:
        raise PromptNotFrozen(f"no frozen {what}: set its file and sha256 in the `extract:` config (ADR-0048 freeze)")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise PromptNotFrozen(f"cannot read the {what} at {path}: {e}") from e
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pinned_sha256:
        raise PromptNotFrozen(f"the {what} at {path} has sha256 {digest}, not the pinned {pinned_sha256}; a changed "
                              "prompt is a new freeze (ADR-0048 section 2)")
    return FrozenText(path, digest, raw.decode("utf-8"))


def draft_text(path: Path) -> FrozenText:
    """An unpinned prompt (measurement only, before the freeze): read as is, hash recorded."""
    raw = path.read_bytes()
    return FrozenText(path, hashlib.sha256(raw).hexdigest(), raw.decode("utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def system_message(prompt: FrozenText, context_block: FrozenText | None, has_context: bool) -> str:
    if has_context:
        if context_block is None:
            raise PromptNotFrozen("a call with context needs the frozen context block")
        return prompt.text.rstrip("\n") + "\n\n" + context_block.text
    return prompt.text


def extraction_messages(prompt: FrozenText, context_block: FrozenText | None, targets: list[tuple[int, str]],
                        context: list[tuple[int, int, str]]) -> list[dict[str, str]]:
    """targets: (window_index, text); context: (window_index, precedes_window_index, text)."""
    user: dict[str, Any] = {"windows": [{"window_index": i, "text": t} for i, t in targets]}
    if context:
        user["context"] = [{"window_index": c, "precedes_window_index": p, "text": t} for c, p, t in context]
    return [
        {"role": "system", "content": system_message(prompt, context_block, bool(context))},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _name(max_len: int = NAME_MAX) -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": max_len}


def extraction_format(target_indices: list[int]) -> dict[str, Any]:
    """Ollama `format` for one call: exactly one record per target window."""
    record = {
        "type": "object",
        "additionalProperties": False,
        "required": ["window_index", "concepts", "relations", "important", "cue", "is_recap"],
        "properties": {
            "window_index": {"type": "integer", "enum": list(target_indices)},
            "concepts": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["label", "aliases"],
                "properties": {"label": _name(), "aliases": {"type": "array", "items": _name()}}}},
            "relations": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["head", "type", "tail"],
                "properties": {"head": _name(), "type": {"type": "string", "enum": list(RELATION_TYPES)},
                               "tail": _name()}}},
            "important": {"type": "boolean"},
            "cue": {"type": ["string", "null"], "maxLength": CUE_MAX},
            "is_recap": {"type": "boolean"},
        },
    }
    n = len(target_indices)
    return {"type": "object", "additionalProperties": False, "required": ["windows"],
            "properties": {"windows": {"type": "array", "minItems": n, "maxItems": n, "items": record}}}


def translation_messages(prompt: FrozenText, text: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": prompt.text},
            {"role": "user", "content": json.dumps({"text": text}, ensure_ascii=False)}]


TRANSLATION_FORMAT: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["english"],
    "properties": {"english": {"type": "string", "minLength": 1}},
}
