"""Stand-in for `python -m insightex.asr.child` in subprocess tests: `python fake_whisper_child.py <mode>`.

Modes: ok, slow (segments with pauses), load_fail, oom_event, oom_stderr, crash, hang, exit_after_ready, garbage_code.
"""

from __future__ import annotations

import json
import sys
import time


def emit(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def seg(i, start, end):
    return {"type": "segment", "id": i, "start": start, "end": end, "text": f" segment {i}", "avg_logprob": -0.1,
            "no_speech_prob": 0.0, "compression_ratio": 1.2, "temperature": 0.0, "words": []}


def main(mode: str) -> int:
    request = json.loads(sys.stdin.read())
    assert request["language"] and request["model_repo"]
    if mode == "load_fail":
        emit({"type": "error", "code": "MODEL_LOAD_FAILED", "detail": "RuntimeError: no such model"})
        return 3
    if mode == "crash":
        sys.stderr.write("Segmentation fault (simulated)\n")
        return 139
    if mode == "oom_stderr":
        sys.stderr.write("RuntimeError: CUDA failed with error out of memory\n")
        return 1
    emit({"type": "ready", "snapshot_path": "/hub/models--Systran--faster-whisper-large-v3/snapshots/feedbeef",
          "load_s": 0.1})
    if mode == "hang":
        time.sleep(60)
        return 0
    if mode == "exit_after_ready":
        return 0
    if mode == "oom_event":
        emit({"type": "error", "code": "GPU_OUT_OF_MEMORY", "detail": "RuntimeError: CUDA failed with error out of memory"})
        return 4
    if mode == "garbage_code":
        emit({"type": "error", "code": "NOT_A_REAL_CODE", "detail": "?"})
        return 4
    for i in range(1, 4):
        if mode == "slow":
            time.sleep(0.3)
        emit(seg(i, (i - 1) * 10.0, i * 10.0))
    emit({"type": "done", "transcribe_s": 1.5, "detected_language": request["language"]})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
