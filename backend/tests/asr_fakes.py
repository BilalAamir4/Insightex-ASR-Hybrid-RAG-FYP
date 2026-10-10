"""Fakes for the ASR stage: no GPU, no Whisper. Installed for every test by conftest unless marked `gpu`."""

from __future__ import annotations

import wave
from typing import Any

from insightex.asr.gpu import Vram


def fake_segments(duration: float, text: str = " fake speech") -> list[dict[str, Any]]:
    """One segment per 10 s of audio, each with two words."""
    out, start, i = [], 0.0, 1
    while start < duration:
        end = min(duration, start + 10.0)
        mid = (start + end) / 2
        out.append({"id": i, "start": start, "end": end, "text": text, "avg_logprob": -0.2, "no_speech_prob": 0.01,
                    "compression_ratio": 1.3, "temperature": 0.0,
                    "words": [{"start": start, "end": mid, "word": " fake", "probability": 0.9},
                              {"start": mid, "end": end, "word": " speech", "probability": 0.8}]})
        start, i = end, i + 1
    return out


class FakeTranscriber:
    """Records each request; returns `segments` (or segments made from the audio length) or raises `error`."""

    def __init__(self, segments: list[dict[str, Any]] | None = None, error: Exception | None = None):
        self.segments, self.error = segments, error
        self.calls: list[Any] = []

    def transcribe(self, request, on_segment, tick):
        from insightex.asr.transcriber import TranscribeResult

        self.calls.append(request)
        tick()
        if self.error is not None:
            raise self.error
        if self.segments is None:
            with wave.open(str(request.audio), "rb") as w:
                segments = fake_segments(w.getnframes() / w.getframerate())
        else:
            segments = [dict(s) for s in self.segments]
        for s in segments:
            on_segment(s)
            tick()
        return TranscribeResult(segments=segments, snapshot_path="/cache/models--x/snapshots/abc123", load_s=1.0,
                                transcribe_s=2.0, peak_vram_mib=4000)


class FakeGpu:
    def __init__(self, free_mib: int = 7000, used_mib: int = 1000):
        self.free_mib, self.used_mib = free_mib, used_mib
        self.queries = 0

    def __call__(self, device_index: int = 0) -> Vram:
        self.queries += 1
        return Vram(self.free_mib, self.used_mib)
