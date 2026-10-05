"""Canonical source ids ("yt:<id>", "gdrive:<id>", "url:<hash>") and the filesystem-safe lecture_id."""

from __future__ import annotations

import re
from pathlib import Path

CANONICAL_ID_RE = re.compile(r"^(yt|gdrive|url):([A-Za-z0-9_-]{1,64})$")
# Prefix, underscore, then only [A-Za-z0-9_-]: no dots, slashes or anything else a path could use.
LECTURE_ID_RE = re.compile(r"^(yt|gdrive|url)_[A-Za-z0-9_-]{1,64}$")


def lecture_id_from_canonical(canonical_id: str) -> str:
    m = CANONICAL_ID_RE.fullmatch(canonical_id)
    if not m:
        raise ValueError(f"invalid canonical id: {canonical_id!r}")
    return f"{m.group(1)}_{m.group(2)}"


def validate_lecture_id(lecture_id: str) -> str:
    if not isinstance(lecture_id, str) or not LECTURE_ID_RE.fullmatch(lecture_id):
        raise ValueError(f"invalid lecture id: {lecture_id!r}")
    return lecture_id


def lecture_dir(root: Path, lecture_id: str) -> Path:
    """<root>/<lecture_id>, refusing anything that would resolve outside root."""
    validate_lecture_id(lecture_id)
    root = Path(root).resolve()
    path = (root / lecture_id).resolve()
    if path.parent != root:
        raise ValueError(f"lecture id escapes the lectures root: {lecture_id!r}")
    return path
