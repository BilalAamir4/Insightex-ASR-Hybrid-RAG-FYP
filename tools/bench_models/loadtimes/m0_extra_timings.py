"""M0 extra timings: bge-m3 load (sentence-transformers) and Whisper warm real-time factor.

Standalone (no backend imports). Each mode runs in its own process; run one at a time.
  python m0_extra_timings.py bge                  # cold load, then warm reload, from $HF_HOME
  python m0_extra_timings.py rtf <medium|large-v3>  # warm transcription of the Day 4 first-10-min audio
Prints one JSON line (__RESULT_JSON__:...). Speed only; no accuracy is measured here.
Cold is only meaningful as the first read after boot (this script does not drop the page cache).
"""
import gc
import json
import os
import sys
import time
from pathlib import Path

AUDIO = Path(os.environ["INSIGHTEX_DATA"]) / "eval/day04_batch_vs_online/eval/lecture_first10min.wav"
WARMUP = Path(os.environ["INSIGHTEX_DATA"]) / "eval/day04_batch_vs_online/eval/clip_30s.wav"


def bge() -> dict:
    import torch
    from sentence_transformers import SentenceTransformer

    times = []
    for _ in range(2):
        t0 = time.time()
        m = SentenceTransformer("BAAI/bge-m3", device="cuda")
        times.append(round(time.time() - t0, 2))
        dim = m.encode(["x"]).shape[1]
        del m
        gc.collect()
        torch.cuda.empty_cache()
    return {"mode": "bge-m3", "cold_s": times[0], "warm_s": times[1], "dim": int(dim)}


def rtf(size: str) -> dict:
    import subprocess

    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(size, device="cuda", compute_type="float16")
    load_s = round(time.time() - t0, 2)
    kw = dict(language="ur", task="transcribe", beam_size=5, temperature=0.0, vad_filter=True)
    segs, _ = model.transcribe(str(WARMUP), **kw)
    list(segs)  # untimed warm-up (CUDA kernels, allocator)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(AUDIO)], text=True))
    t0 = time.time()
    segs, info = model.transcribe(str(AUDIO), **kw)
    n = sum(1 for _ in segs)  # consume the generator: this is where decoding happens
    infer_s = time.time() - t0
    return {"mode": f"whisper-{size}", "load_s": load_s, "audio_s": round(dur, 1), "infer_s": round(infer_s, 2),
            "rtf": round(infer_s / dur, 4), "x_realtime": round(dur / infer_s, 2), "segments": n,
            "settings": "language=ur task=transcribe beam_size=5 temperature=0.0 vad_filter=True fp16"}


if __name__ == "__main__":
    r = bge() if sys.argv[1] == "bge" else rtf(sys.argv[2])
    print("__RESULT_JSON__:" + json.dumps(r))
