"""C2 arm B translation stage (ADR-0048 section 8 and Amendment 8): per-window English made by the C1 winner.

Cache. One translation per window, stored as its own stage under `extract.translation_cache_path()`, keyed by the
sha256 of exactly three things: the window text's sha256, the model digest and the translation prompt's sha256. The
harness version, the attempt number and the call options are not in the key, so extraction reruns and harness
version bumps reuse the stored translations. Only translations that passed the check below are stored; a window whose
translation failed twice is not stored, and arm B fails closed on it.

Check. A translation reply is valid when it parses as `{"english": <string>}`, the string is not blank, it has at
least one letter, and no more than `extract.translate_max_non_latin_fraction` of its letters are Arabic-script or
Devanagari (Amendment 8: the English check).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import unicodedata
from pathlib import Path
from typing import Any

TRANSLATION_CACHE_VERSION = 1  # layout of a stored entry (not in the key)

# Unicode blocks counted as "not English" by the English check
NON_LATIN_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x0870, 0x089F),  # Arabic Extended-B
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
    (0x0900, 0x097F),  # Devanagari
    (0xA8E0, 0xA8FF),  # Devanagari Extended
)


def _non_latin(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in NON_LATIN_RANGES)


def non_latin_fraction(text: str) -> float | None:
    """Share of the letters (Unicode L*, plus combining marks M* of those scripts) that are Arabic-script or
    Devanagari; None when the text has no letters."""
    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")
               or (unicodedata.category(ch).startswith("M") and _non_latin(ch))]
    if not letters:
        return None
    return sum(1 for ch in letters if _non_latin(ch)) / len(letters)


def check_translation(content: str | None, error: str | None, max_non_latin: float) -> tuple[str | None, list[str]]:
    """(english, errors) for one translation reply; english is None when the reply is invalid."""
    if content is None:
        return None, [error or "no reply"]
    try:
        obj = json.loads(content)
    except ValueError as e:
        return None, [f"reply is not JSON: {e}"]
    english = obj.get("english") if isinstance(obj, dict) else None
    if not isinstance(english, str):
        return None, ["reply has no `english` string"]
    if not english.strip():
        return None, ["`english` is blank"]
    frac = non_latin_fraction(english)
    if frac is None:
        return None, ["`english` has no letters"]
    if frac > max_non_latin:
        return None, [(f"`english` is not English: {frac:.1%} of its letters are Arabic-script or Devanagari "
                       f"(at most {max_non_latin:.0%} allowed); translate everything into English")]
    return english, []


def translation_key(window_text_sha256: str, model_digest: str, prompt_sha256: str) -> str:
    """The stage key (ADR-0048 section 8): window text sha256, model digest and translation prompt sha256 only."""
    fields = {"window_text_sha256": window_text_sha256, "model_digest": model_digest, "prompt_sha256": prompt_sha256}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class TranslationCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def put(self, *, window_text_sha256: str, model: str, model_digest: str, prompt_sha256: str, english: str,
            attempt_used: int, call: dict[str, Any]) -> str:
        key = translation_key(window_text_sha256, model_digest, prompt_sha256)
        entry = {"cache_version": TRANSLATION_CACHE_VERSION, "key": key,
                 "key_fields": {"window_text_sha256": window_text_sha256, "model_digest": model_digest,
                                "prompt_sha256": prompt_sha256},
                 "model": model, "english": english, "attempt_used": attempt_used,
                 "call": {k: call.get(k) for k in ("metrics", "wall_s", "ps", "harness_version")},
                 "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        return key
