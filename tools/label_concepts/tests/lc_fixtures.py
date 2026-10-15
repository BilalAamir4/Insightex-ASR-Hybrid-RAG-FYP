"""Synthetic lecture workspaces and label records for the label_concepts tests (no real lecture text)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def segment(i: int, start: float, end: float, text: str) -> dict[str, Any]:
    return {"id": i, "start": start, "end": end, "text": text}


def make_workspace(root: Path, lecture_id: str, segments: list[dict[str, Any]], duration_s: float,
                   tier: str = "tested", index_windows: list[dict[str, Any]] | None = None) -> Path:
    ws = root / "workspaces" / lecture_id
    stages: dict[str, Any] = {"asr": {"key": "a1"}, "normalise": {"key": "n1"}}
    (ws / "stages" / "asr" / "a1").mkdir(parents=True)
    (ws / "stages" / "normalise" / "n1").mkdir(parents=True)
    transcript = {"audio": {"duration_s": duration_s},
                  "language": {"id": "hindi", "tier_at_processing": tier}, "segments": segments}
    (ws / "stages" / "asr" / "a1" / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    (ws / "stages" / "normalise" / "n1" / "video.mp4").write_bytes(bytes(range(256)) * 4)
    if index_windows is not None:
        (ws / "stages" / "index" / "i1").mkdir(parents=True)
        (ws / "stages" / "index" / "i1" / "windows.json").write_text(
            json.dumps({"schema_version": 2, "windows": index_windows}), encoding="utf-8")
        stages["index"] = {"key": "i1", "fingerprint": {"window_s": 30.0, "stride_s": 30.0,
                                                        "snap_to_segments": False}}
    (ws / "manifest.json").write_text(json.dumps({"workspace_id": lecture_id, "stages": stages}), encoding="utf-8")
    return ws


def toy_segments(n_windows: int) -> list[dict[str, Any]]:
    """Two segments per 30 s window, with text 'w<k> a' and 'w<k> b'."""
    out = []
    for k in range(n_windows):
        out.append(segment(2 * k, 30 * k + 1, 30 * k + 10, f"w{k} a"))
        out.append(segment(2 * k + 1, 30 * k + 12, 30 * k + 25, f"w{k} b"))
    return out


def concept(label: str, *aliases: str) -> dict[str, Any]:
    return {"label": label, "aliases": list(aliases)}


def rel(head: str, rtype: str, tail: str) -> dict[str, str]:
    return {"head": head, "type": rtype, "tail": tail}


def labels(concepts=(), relations=(), important=False, cue=None) -> dict[str, Any]:
    return {"concepts": list(concepts), "relations": list(relations), "important": important, "cue": cue}


def record(lecture_id: str, index: int, start: float, end: float, **kw: Any) -> dict[str, Any]:
    return {"window": {"lecture_id": lecture_id, "window_index": index, "start_s": start, "end_s": end},
            **labels(**kw)}
