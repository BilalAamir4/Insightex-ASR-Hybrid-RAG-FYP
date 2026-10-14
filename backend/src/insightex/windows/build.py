"""Transcript segments -> search windows (M5, ADR-0043, ADR-0044).

Pure functions, no model and no GPU. A window is a time slice of the lecture and the text spoken in it.
Times are seconds on the `audio.wav` timeline, which equals the video timeline (ADR-0038).
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = 2  # 2: windows carry first_segment_start (ADR-0047)


@dataclass(frozen=True)
class Window:
    id: int
    start: float  # seconds; the grid start k * stride_s
    end: float  # seconds; start + window_s, clipped to the audio duration
    first_segment: int  # transcript segment id of the first segment in the window
    first_segment_start: float  # seconds; where a citation seeks to (ADR-0044, ADR-0047)
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
                first_segment=int(members[0][0]["id"]), first_segment_start=float(members[0][0]["start"]),
                last_segment=int(members[-1][0]["id"]),
                n_segments=len(members), text=" ".join(t for _, t in members),
            ))
        k += 1
    return out


def build_snapped_windows(segments: list[dict[str, Any]], *, window_s: float, stride_s: float) -> list[Window]:
    """Windows whose edges are segment boundaries (ADR-0043 gate G3).

    A window starts at a segment's start and ends at the end of the segment that lies closest to `start + window_s`
    (among segments starting before that point; ties go to the earlier one); it always holds at least one segment.
    Window start and end are the first segment's start and the last segment's end, so silence between windows is not
    covered. The next window starts:

    - `stride_s == window_s` (no overlap): at the segment after the last one included;
    - otherwise: at the segment whose start is closest to `start + stride_s` (ties go to the later one), always
      after the current start.

    Windowing stops once a window contains the last segment, because later windows would lie inside it.
    Empty segments are skipped; window ids count the windows.
    """
    segs = [(s, window_text(s["text"])) for s in segments]
    segs = [(s, t) for s, t in segs if t]
    out: list[Window] = []
    i = 0
    while i < len(segs):
        t0 = float(segs[i][0]["start"])
        target = t0 + window_s
        last = i
        best = abs(float(segs[i][0]["end"]) - target)
        for j in range(i + 1, len(segs)):
            if float(segs[j][0]["start"]) >= target:
                break
            gap = abs(float(segs[j][0]["end"]) - target)
            if gap < best:
                last, best = j, gap
        members = segs[i:last + 1]
        out.append(Window(
            id=len(out), start=t0, end=float(members[-1][0]["end"]), first_segment=int(members[0][0]["id"]),
            first_segment_start=float(members[0][0]["start"]), last_segment=int(members[-1][0]["id"]), n_segments=len(members), text=" ".join(t for _, t in members),
        ))
        if last == len(segs) - 1:
            break
        if stride_s == window_s:
            i = last + 1
        else:
            want = t0 + stride_s
            i = min(range(i + 1, len(segs)), key=lambda k: (abs(float(segs[k][0]["start"]) - want), -k))
    return out
