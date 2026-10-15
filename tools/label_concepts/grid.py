"""Lecture workspace access and the 30 s window grid, reimplemented locally (tools never import backend/).

The grid MUST match the production index stage (ADR-0044, ADR-0045; backend/src/insightex/windows/build.py,
`build_windows`): window k covers [k * stride_s, k * stride_s + window_s), clipped to the audio duration; a segment
belongs to the window its START falls in; segment text is NFC and stripped; window text is the member texts joined
with one space; windows with no text are dropped and window ids count the kept windows. If the lecture has an index
stage, `check_against_index` compares this grid with its windows.json and the sampler refuses to run on a mismatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WINDOW_S = 30.0  # seconds; ADR-0045 window length
STRIDE_S = 30.0  # seconds; ADR-0045 stride (no overlap)


@dataclass(frozen=True)
class GridWindow:
    index: int
    start_s: float
    end_s: float
    text: str

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def data_dir(explicit: str | None = None) -> Path:
    return Path(explicit or os.environ.get("INSIGHTEX_DATA") or Path.home() / "insightex-data")


class Workspace:
    """A lecture workspace: $INSIGHTEX_DATA/workspaces/<lecture_id>/, stage outputs under stages/<stage>/<key>/."""

    def __init__(self, root: Path, lecture_id: str):
        self.lecture_id = lecture_id
        self.dir = root / "workspaces" / lecture_id
        manifest = self.dir / "manifest.json"
        if not manifest.is_file():
            raise SystemExit(f"no workspace manifest at {manifest}")
        self.manifest = json.loads(manifest.read_text(encoding="utf-8"))

    def stage_file(self, stage: str, name: str) -> Path | None:
        entry = self.manifest.get("stages", {}).get(stage)
        if not entry or "key" not in entry:
            return None
        path = self.dir / "stages" / stage / entry["key"] / name
        return path if path.is_file() else None

    def transcript(self) -> dict[str, Any]:
        path = self.stage_file("asr", "transcript.json")
        if path is None:
            raise SystemExit(f"{self.lecture_id}: no asr stage output (transcript.json); ingest it with a language first")
        return json.loads(path.read_text(encoding="utf-8"))

    def video(self) -> Path:
        path = self.stage_file("normalise", "video.mp4")
        if path is None:
            raise SystemExit(f"{self.lecture_id}: no normalise stage output (video.mp4)")
        return path


def _segment_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def build_grid(segments: list[dict[str, Any]], duration_s: float, window_s: float = WINDOW_S,
               stride_s: float = STRIDE_S) -> list[GridWindow]:
    texts = [(float(s["start"]), _segment_text(s["text"])) for s in segments]
    texts = [(st, t) for st, t in texts if t]
    if not texts or duration_s <= 0:
        return []
    out: list[GridWindow] = []
    k = 0
    while True:
        start = round(k * stride_s, 6)
        if start >= duration_s:
            break
        nominal_end = start + window_s
        members = [t for st, t in texts if start <= st < nominal_end]
        if members:
            out.append(GridWindow(len(out), start, round(min(nominal_end, duration_s), 6), " ".join(members)))
        k += 1
    return out


def lecture_grid(ws: Workspace) -> tuple[list[GridWindow], dict[str, Any]]:
    """The lecture's grid windows and facts about the transcript they came from."""
    doc = ws.transcript()
    duration = float(doc["audio"]["duration_s"])
    windows = build_grid(doc["segments"], duration)
    info = {
        "duration_s": duration,
        "language_id": doc.get("language", {}).get("id"),
        "language_tier_at_processing": doc.get("language", {}).get("tier_at_processing"),
        "asr_key": ws.manifest["stages"]["asr"]["key"],
        "segment_count": len(doc["segments"]),
    }
    return windows, info


def check_against_index(ws: Workspace, windows: list[GridWindow]) -> str:
    """'match' if the index stage's windows.json has the same ids, times and texts; 'no index' if the lecture has no
    index stage. Raises SystemExit on any difference."""
    path = ws.stage_file("index", "windows.json")
    if path is None:
        return "no index"
    entry = ws.manifest["stages"]["index"]
    fp = entry.get("fingerprint", {})
    if fp.get("snap_to_segments") or float(fp.get("window_s", WINDOW_S)) != WINDOW_S \
            or float(fp.get("stride_s", STRIDE_S)) != STRIDE_S:
        raise SystemExit(f"{ws.lecture_id}: the index stage was built with other window settings ({fp}); "
                         "the labelling grid is the ADR-0045 fixed 30 s grid")
    prod = json.loads(path.read_text(encoding="utf-8"))["windows"]
    if len(prod) != len(windows):
        raise SystemExit(f"{ws.lecture_id}: {len(windows)} local windows but {len(prod)} in the index stage")
    for p, w in zip(prod, windows):
        if (p["id"], float(p["start"]), float(p["end"]), p["text"]) != (w.index, w.start_s, w.end_s, w.text):
            raise SystemExit(f"{ws.lecture_id}: window {w.index} differs from the index stage's windows.json")
    return "match"
