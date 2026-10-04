import sys
import json
import time
from pathlib import Path
from faster_whisper import WhisperModel

MODEL_CACHE = "/home/bilal_aamir/cache/huggingface/hub"
AUDIO_FILE = "/mnt/e/FYP/data/day04_batch_vs_online/eval/clip_30s.wav"

def run_test(model_name, temp_override, runs_count=2):
    print(f"Loading {model_name} (compute_type=float16, device=cuda)...", file=sys.stderr)
    t0 = time.time()
    model = WhisperModel(model_name, device="cuda", compute_type="float16", download_root=MODEL_CACHE)
    load_time = time.time() - t0
    print(f"Loaded in {load_time:.2f}s", file=sys.stderr)

    results = []
    for r in range(1, runs_count + 1):
        is_cold = (r == 1)
        t_start = time.time()
        
        kwargs = dict(
            language="ur",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        if temp_override is not None:
            kwargs["temperature"] = temp_override

        segments_gen, info = model.transcribe(AUDIO_FILE, **kwargs)
        segs = []
        for s in segments_gen:
            segs.append({
                "id": s.id,
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.text,
                "avg_logprob": round(s.avg_logprob, 4),
                "compression_ratio": round(s.compression_ratio, 4),
                "no_speech_prob": round(s.no_speech_prob, 4),
                "temperature": round(s.temperature, 2)
            })
        elapsed = time.time() - t_start
        results.append({
            "run": r,
            "is_cold": is_cold,
            "elapsed_s": round(elapsed, 4),
            "num_segments": len(segs),
            "segments": segs
        })
        print(f"Run {r} ({'cold' if is_cold else 'warm'}): {elapsed:.2f}s, {len(segs)} segments", file=sys.stderr)

    return {
        "model": model_name,
        "temperature_override": temp_override,
        "load_time_s": round(load_time, 2),
        "runs": results
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_F3_segments.py <model_name> <temp_override_or_none>")
        sys.exit(1)
    
    m_name = sys.argv[1]
    t_val = None if sys.argv[2].lower() in ["none", "default"] else float(sys.argv[2])
    data = run_test(m_name, t_val, runs_count=2)
    print(json.dumps(data))
