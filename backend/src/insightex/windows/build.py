"""Transcript segments -> search windows (M5, ADR-0043, ADR-0044).

Pure functions, no model and no GPU. A window is a time slice of the lecture and the text spoken in it.
Times are seconds on the `audio.wav` timeline, which equals the video timeline (ADR-0038).
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Window:
    id: int
    start: float  # seconds; the grid start k * stride_s
    end: float  # seconds; start + window_s, clipped to the audio duration
    first_segment: int  # transcript segment id of the first segment in the window
    last_segment: int
    n_segments: int
    text: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def window_text(segment_text: str) -> str:
    """One segment's text as embedded: NFC, surrounding whitespace removed. Nothing else is changed."""
    return unicodedata.normalize("NFC", segment_text).strip()


def build_windows(segments: list[dict[str, Any]], *, window_s: float, stride_s: float, duration_s: float) -> list[Window]:
    """Fixed-grid windows: window k covers [k * stride_s, k * stride_s + window_s).

    A segment belongs to a window if its START time falls inside it (the bake-off's rule), so with
    `stride_s == window_s` every segment is in exactly one window. Window text is the member segments
    joined with a single space. Windows with no text are dropped; window ids count the kept windows.
    """
    texts = [(s, window_text(s["text"])) for s in segments]
    texts = [(s, t) for s, t in texts if t]
    if not texts or duration_s <= 0:
        return []
    out: list[Window] = []
    k = 0
    while True:
        start = round(k * stride_s, 6)
        if start >= duration_s:
            break
        nominal_end = start + window_s
        members = [(s, t) for s, t in texts if start <= s["start"] < nominal_end]
        if members:
            out.append(Window(
                id=len(out), start=start, end=round(min(nominal_end, duration_s), 6),
                first_segment=int(members[0][0]["id"]), last_segment=int(members[-1][0]["id"]),
                n_segments=len(members), text=" ".join(t for _, t in members),
            ))
        k += 1
    return out
