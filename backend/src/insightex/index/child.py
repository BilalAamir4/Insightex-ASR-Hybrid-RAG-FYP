"""The encoder subprocess: `python -m insightex.index.child` (ADR-0044).

Reads one JSON request on stdin, loads BGE-M3 from the offline cache, encodes the window texts and saves
the vectors, then exits so the process takes its VRAM with it. NDJSON events on stdout, one per line:

    {"type": "ready", "load_s": ...}
    {"type": "done", "encode_s": ..., "count": ..., "dim": ..., "n_truncated": ..., "peak_allocated_mib": ...}
    {"type": "error", "code": "<ErrorCode>", "detail": "..."}                       (instead of done)

The request carries everything (nothing here reads settings): texts_path (JSON list of strings), out_path (.npy),
model_repo, model_revision, device, device_index, dtype, max_seq_length, batch_size.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _is_oom(exc: BaseException) -> bool:
    return "out of memory" in str(exc).lower()


def main() -> int:
    req = json.loads(sys.stdin.read())
    try:
        import numpy as np
        import torch

        from insightex.index import model as m

        texts = json.loads(Path(req["texts_path"]).read_text(encoding="utf-8"))
        t0 = time.monotonic()
        model = m.load_model(req["model_repo"], req["model_revision"], device=req["device"],
                             device_index=req["device_index"], dtype=req["dtype"], max_seq_length=req["max_seq_length"])
        load_s = time.monotonic() - t0
    except Exception as exc:  # noqa: BLE001 - reported to the parent as a coded event
        _emit({"type": "error", "code": "GPU_OUT_OF_MEMORY" if _is_oom(exc) else "MODEL_LOAD_FAILED",
               "detail": f"{type(exc).__name__}: {exc}"})
        return 3
    _emit({"type": "ready", "load_s": round(load_s, 3)})
    try:
        if req["device"] == "cuda":
            torch.cuda.reset_peak_memory_stats()
        t0 = time.monotonic()
        vectors = m.encode(model, texts, req["batch_size"])
        encode_s = time.monotonic() - t0
        n_truncated = m.count_truncated(model, texts, req["max_seq_length"])
        np.save(req["out_path"], vectors, allow_pickle=False)
        peak = torch.cuda.max_memory_allocated() / (1024 * 1024) if req["device"] == "cuda" else None
        _emit({"type": "done", "encode_s": round(encode_s, 3), "count": int(vectors.shape[0]), "dim": int(vectors.shape[1]),
               "n_truncated": n_truncated, "peak_allocated_mib": None if peak is None else round(peak, 1)})
    except Exception as exc:  # noqa: BLE001 - reported to the parent as a coded event
        _emit({"type": "error", "code": "GPU_OUT_OF_MEMORY" if _is_oom(exc) else "ENCODE_CRASHED",
               "detail": f"{type(exc).__name__}: {exc}"})
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
