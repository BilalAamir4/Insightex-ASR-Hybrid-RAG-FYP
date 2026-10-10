"""The Whisper subprocess: `python -m insightex.asr.child` (ADR-0042).

Reads one JSON request on stdin, loads the model from the offline cache, transcribes, and writes NDJSON
events to stdout, one per line, then exits so the process takes its VRAM with it:

    {"type": "ready", "snapshot_path": ..., "load_s": ...}
    {"type": "segment", "id": ..., "start": ..., "end": ..., "text": ..., ..., "words": [...]}   (one per segment)
    {"type": "done", "transcribe_s": ..., "detected_language": ...}
    {"type": "error", "code": "<ErrorCode>", "detail": "..."}                                  (instead of done)

The caller is the ASR stage in the worker. Nothing here reads settings: the request carries everything.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _is_oom(exc: BaseException) -> bool:
    return "out of memory" in str(exc).lower()


def _params(raw: dict[str, Any]) -> dict[str, Any]:
    """The transcribe() keyword arguments; "inf" strings (JSON has no infinity) become floats again."""
    params = dict(raw)
    vad = params.get("vad_parameters")
    if isinstance(vad, dict):
        params["vad_parameters"] = {k: float(v) if v in ("inf", "-inf") else v for k, v in vad.items()}
    return params


def main() -> int:
    request = json.loads(sys.stdin.read())
    try:
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model

        t0 = time.monotonic()
        path = download_model(request["model_repo"], local_files_only=True, revision=request["model_revision"])
        model = WhisperModel(
            path, device=request["device"], device_index=request["device_index"], compute_type=request["compute_type"],
            cpu_threads=request["cpu_threads"], num_workers=request["num_workers"], local_files_only=True,
        )
        load_s = time.monotonic() - t0
    except Exception as exc:  # noqa: BLE001 - reported to the parent as a coded event
        _emit({"type": "error", "code": "GPU_OUT_OF_MEMORY" if _is_oom(exc) else "MODEL_LOAD_FAILED",
               "detail": f"{type(exc).__name__}: {exc}"})
        return 3
    _emit({"type": "ready", "snapshot_path": str(path), "load_s": round(load_s, 3)})
    try:
        t0 = time.monotonic()
        segments, info = model.transcribe(request["audio"], language=request["language"], **_params(request["params"]))
        for s in segments:  # a generator: consuming it is the transcription
            _emit({
                "type": "segment", "id": s.id, "start": round(s.start, 3), "end": round(s.end, 3), "text": s.text,
                "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob,
                "compression_ratio": s.compression_ratio, "temperature": s.temperature,
                "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word, "probability": w.probability}
                          for w in (s.words or [])],
            })
        _emit({"type": "done", "transcribe_s": round(time.monotonic() - t0, 3), "detected_language": info.language})
    except Exception as exc:  # noqa: BLE001 - reported to the parent as a coded event
        _emit({"type": "error", "code": "GPU_OUT_OF_MEMORY" if _is_oom(exc) else "TRANSCRIBE_CRASHED",
               "detail": f"{type(exc).__name__}: {exc}"})
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
