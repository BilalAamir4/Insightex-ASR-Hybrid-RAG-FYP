"""transcript.json (the single source of truth) and transcript.vtt (a developer check only) (ADR-0042).

Pure functions plus atomic writers; no Whisper, no GPU. Times are seconds on the audio.wav timeline,
which equals the video timeline (ADR-0038). Text is stored exactly as Whisper returned it.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
TRANSCRIPT_JSON, TRANSCRIPT_VTT = "transcript.json", "transcript.vtt"


def json_safe(value: Any) -> Any:
    """`value` with every infinite float replaced by the string "inf" / "-inf" (JSON has no infinity)."""
    if isinstance(value, float) and math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def _ms(t: float) -> float:
    return round(float(t), 3)


def clean_segment(seg: dict[str, Any]) -> dict[str, Any]:
    """One segment in the transcript shape: times rounded to milliseconds, text untouched."""
    return {
        "id": int(seg["id"]),
        "start": _ms(seg["start"]),
        "end": _ms(seg["end"]),
        "text": seg["text"],
        "avg_logprob": float(seg["avg_logprob"]),
        "no_speech_prob": float(seg["no_speech_prob"]),
        "compression_ratio": float(seg["compression_ratio"]),
        "temperature": float(seg["temperature"]),
        "words": [{"start": _ms(w["start"]), "end": _ms(w["end"]), "word": w["word"], "probability": float(w["probability"])}
                  for w in seg.get("words") or []],
    }


def is_empty(segments: list[dict[str, Any]]) -> bool:
    """No segments, or only whitespace text."""
    return not any(s["text"].strip() for s in segments)


def find_warnings(segments: list[dict[str, Any]], warn_compression_ratio: float) -> list[dict[str, Any]]:
    """TEMPERATURE_FALLBACK (temperature > 0) and HIGH_COMPRESSION_RATIO (> threshold); the stage still succeeds."""
    warnings = []
    fallback = [s["id"] for s in segments if s["temperature"] > 0]
    if fallback:
        warnings.append({
            "code": "TEMPERATURE_FALLBACK",
            "message": f"{len(fallback)} segment(s) needed temperature fallback; their text can differ between runs.",
            "segment_ids": fallback,
        })
    high = [s["id"] for s in segments if s["compression_ratio"] > warn_compression_ratio]
    if high:
        warnings.append({
            "code": "HIGH_COMPRESSION_RATIO",
            "message": f"{len(high)} segment(s) have a compression ratio above {warn_compression_ratio:g}, "
                       f"a sign of repeated or hallucinated text.",
            "segment_ids": high,
        })
    return warnings


def build_transcript(
    *,
    stage_version: str,
    language: dict[str, str],
    model: dict[str, Any],
    params: dict[str, Any],
    libraries: dict[str, str],
    audio: dict[str, Any],
    segments: list[dict[str, Any]],
    wall_time_s: float,
    peak_vram_mib: int | None,
    warn_compression_ratio: float,
) -> dict[str, Any]:
    """The transcript.json document. `segments` must already be cleaned (`clean_segment`)."""
    duration = float(audio["duration_s"])
    return {
        "schema_version": SCHEMA_VERSION,
        "stage_version": stage_version,
        "language": language,
        "model": model,
        "params": json_safe(params),
        "libraries": libraries,
        "audio": audio,
        "stats": {
            "segment_count": len(segments),
            "fallback_segment_count": sum(1 for s in segments if s["temperature"] > 0),
            "high_compression_segment_count": sum(1 for s in segments if s["compression_ratio"] > warn_compression_ratio),
            "wall_time_s": round(wall_time_s, 3),
            "rtf": round(wall_time_s / duration, 4) if duration > 0 else None,
            "peak_vram_mib": peak_vram_mib,
        },
        "warnings": find_warnings(segments, warn_compression_ratio),
        "segments": segments,
    }


def vtt_timestamp(t: float) -> str:
    """HH:MM:SS.mmm (hours keep counting past 99 minutes; WebVTT allows two or more hour digits)."""
    ms = round(float(t) * 1000)
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_vtt(segments: list[dict[str, Any]]) -> str:
    """WebVTT with one cue per segment, identified by the segment id. Cue text is the segment text on one line."""
    out = ["WEBVTT", ""]
    for s in segments:
        text = " ".join(s["text"].split()) or "[no text]"
        out += [str(s["id"]), f"{vtt_timestamp(s['start'])} --> {vtt_timestamp(s['end'])}", text.replace("-->", "->"), ""]
    return "\n".join(out)


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temp file in the same directory, fsync, then rename over `path`.

    A crash at any point leaves either no `path` or a complete one, never a partial file under the final name.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def dumps(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False) + "\n"


class ProgressThrottle:
    """Decides when a new progress value is reported: only when both thresholds are crossed since the last report."""

    def __init__(self, min_interval_s: float, min_step: float) -> None:
        self.min_interval_s, self.min_step = min_interval_s, min_step
        self.last_value = 0.0
        self._last_time: float | None = None

    def offer(self, value: float, now: float) -> bool:
        """True (and remember it) if `value` should be reported at time `now`."""
        if self._last_time is not None and now - self._last_time < self.min_interval_s:
            return False
        if value - self.last_value < self.min_step - 1e-12:
            return False
        self.last_value, self._last_time = value, now
        return True

    def start(self, now: float) -> None:
        """The stage reported 0 at `now`; the first update needs both thresholds from there."""
        self._last_time = now
