import sys
import traceback

try:
    from faster_whisper import WhisperModel
    model_path = "/home/bilal_aamir/cache/huggingface/hub"
    audio_file = "/mnt/e/FYP/data/day04_batch_vs_online/eval/clip_30s.wav"
    print("Initializing WhisperModel('medium', device='cuda', compute_type='float16')...", flush=True)
    model = WhisperModel("medium", device="cuda", compute_type="float16", download_root=model_path)
    print("Model loaded. Transcribing...", flush=True)
    segments, info = model.transcribe(audio_file, language="ur")
    first_seg = next(segments)
    print(f"SUCCESS: Transcribed segment: {first_seg.text}", flush=True)
except Exception as e:
    print(f"FAILED WITH EXCEPTION: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
