"""Request building for M7 extraction and translation calls (ADR-0048, Amendment 2).

No prompt wording lives here. The instructions are the frozen files named in the `extract:` config (the extraction
prompt, the C4 context block and the C2 translation prompt), each used only when its sha256 equals the pinned value.
This module only arranges data around them:

- system message: the extraction prompt's instructions, followed by the context block when (and only when) the call
  carries context. A call without context (C4 arm B on the lecture's first window) is therefore byte-identical to
  arm A's;
- retry (all arms): the same call again, in the same unit (a single window stays single, a batch stays a batch),
  with one more user message: the retry template with the first attempt's validation errors in place of `{errors}`.
  The template is the part of the extraction prompt file after a line that is exactly `<<<RETRY>>>`, so it is frozen
  and hashed with the prompt; a prompt file without exactly one such line, or whose template does not contain
  `{errors}` exactly once, is refused (Session 2b decision 3);
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

from insightex.extract.extraction_schema import CUE_MAX, LIST_MAX, NAME_MAX, RELATION_TYPES

USER_FORMAT_VERSION = 1
FORMAT_VERSION = 2  # 2: concepts and relations capped at LIST_MAX items


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


RETRY_MARKER = "<<<RETRY>>>"
ERRORS_SLOT = "{errors}"


def split_extraction_prompt(prompt: FrozenText) -> tuple[str, str]:
    """(instructions, retry template) of an extraction prompt file; raises PromptNotFrozen if the retry section is
    missing or malformed."""
    lines = prompt.text.split("\n")
    marks = [i for i, line in enumerate(lines) if line.strip() == RETRY_MARKER]
    if len(marks) != 1:
        raise PromptNotFrozen(f"the extraction prompt at {prompt.path} needs exactly one line `{RETRY_MARKER}` "
                              f"followed by the retry template (found {len(marks)})")
    instructions = "\n".join(lines[:marks[0]]).rstrip("\n") + "\n"
    template = "\n".join(lines[marks[0] + 1:]).strip("\n")
    if template.count(ERRORS_SLOT) != 1:
        raise PromptNotFrozen(f"the retry template in {prompt.path} must contain {ERRORS_SLOT} exactly once")
    return instructions, template


def errors_text(errors: list[str], max_chars: int) -> str:
    """The validation errors quoted in a retry message, one per line, cut at `max_chars` with a count of the rest."""
    lines, used = [], 0
    for i, e in enumerate(errors):
        line = f"- {e}"
        if used + len(line) + 1 > max_chars:
            lines.append(f"- ... and {len(errors) - i} more")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def retry_messages(messages: list[dict[str, str]], prompt: FrozenText, errors: list[str],
                   max_chars: int) -> list[dict[str, str]]:
    """The first attempt's messages plus the retry template carrying its validation errors."""
    _, template = split_extraction_prompt(prompt)
    return [*messages, {"role": "user", "content": template.replace(ERRORS_SLOT, errors_text(errors, max_chars))}]


def draft_text(path: Path) -> FrozenText:
    """An unpinned prompt (measurement only, before the freeze): read as is, hash recorded."""
    raw = path.read_bytes()
    return FrozenText(path, hashlib.sha256(raw).hexdigest(), raw.decode("utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def system_message(prompt: FrozenText, context_block: FrozenText | None, has_context: bool) -> str:
    instructions, _ = split_extraction_prompt(prompt)
    if has_context:
        if context_block is None:
            raise PromptNotFrozen("a call with context needs the frozen context block")
        return instructions.rstrip("\n") + "\n\n" + context_block.text
    return instructions


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
            "concepts": {"type": "array", "maxItems": LIST_MAX, "items": {
                "type": "object", "additionalProperties": False, "required": ["label", "aliases"],
                "properties": {"label": _name(), "aliases": {"type": "array", "items": _name()}}}},
            "relations": {"type": "array", "maxItems": LIST_MAX, "items": {
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
