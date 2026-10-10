"""Transcribe one audio file with one faster-whisper config (run as its own subprocess).

Loads the model, does one discarded warm-up transcription (--warmup-audio), then a
timed transcription. Writes raw JSON: segments, words, detected language, options, timing.
Standalone: no imports from backend/.
"""
import argparse
import dataclasses
import json
import sys
import time

# Parameters identical for every config (recorded in the output JSON).
FIXED = dict(task="transcribe", beam_size=5, vad_filter=True, word_timestamps=True)
DEVICE, COMPUTE = "cuda", "float16"


def run(model, audio, language):
    segs, info = model.transcribe(audio, language=language, **FIXED)
    out = []
    for s in segs:  # generator: consuming it is the transcription
        out.append(dict(
            id=s.id, start=round(s.start, 3), end=round(s.end, 3), text=s.text,
            avg_logprob=s.avg_logprob, no_speech_prob=s.no_speech_prob,
            temperature=s.temperature, compression_ratio=s.compression_ratio,
            words=[dict(start=round(w.start, 3), end=round(w.end, 3), word=w.word,
                        probability=round(w.probability, 4)) for w in (s.words or [])]))
    return out, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--language", default="auto", help="'auto' means language=None")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--warmup-audio", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lang = None if a.language == "auto" else a.language

    import faster_whisper
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    t0 = time.time()
    model = WhisperModel(a.model, device=DEVICE, compute_type=COMPUTE)
    load_s = time.time() - t0
    print("READY", flush=True)  # parent starts VRAM polling baseline-relative
    run(model, a.warmup_audio, lang)  # discarded
    duration = len(decode_audio(a.audio)) / 16000
    t0 = time.time()
    segments, info = run(model, a.audio, lang)
    wall = time.time() - t0
    json.dump(dict(
        model=a.model, language_setting=a.language, audio=a.audio, faster_whisper=faster_whisper.__version__,
        device=DEVICE, compute_type=COMPUTE, fixed_params=FIXED,
        transcription_options={k: repr(v) for k, v in dataclasses.asdict(info.transcription_options).items()},
        vad_options=repr(info.vad_options),
        detected_language=info.language, language_probability=info.language_probability,
        audio_seconds=duration, load_seconds=round(load_s, 2), transcribe_seconds=round(wall, 2),
        warm_rtf=round(wall / duration, 4), segments=segments), open(a.out, "w"), ensure_ascii=False, indent=1)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
