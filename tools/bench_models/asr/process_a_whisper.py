#!/usr/bin/env python3
"""
TASK T2 - Process A:
Extracts first 10 minutes of lecture_test.mp4 to 16 kHz mono WAV,
transcribes with faster-whisper large-v3 (CUDA float16, language='ur', beam=5, VAD on),
and saves segments to whisper_large_v3_first10min.json.
"""
import os
import sys
import time
import json
import subprocess
import threading
from pathlib import Path

VIDEO_FILE = os.path.join(os.environ["INSIGHTEX_DATA"], "eval/day04_batch_vs_online/raw/lecture_test.mp4")
AUDIO_FILE = os.path.join(os.environ["INSIGHTEX_DATA"], "eval/day04_batch_vs_online/eval/lecture_first10min.wav")
OUT_JSON = os.path.join(os.environ["INSIGHTEX_DATA"], "eval/day04_batch_vs_online/eval/whisper_large_v3_first10min.json")
CACHE_DIR = os.path.expanduser("~/cache/huggingface/hub")
NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"

def get_vram_mb():
    try:
        out = subprocess.check_output(
            [NVIDIA_SMI, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=5
        )
        return int(out.strip().split("\n")[0])
    except Exception:
        return 0

class VRAMSampler:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.stop_event = threading.Event()
        self.peak_vram = 0
        self.baseline_vram = 0

    def _monitor(self):
        while not self.stop_event.is_set():
            v = get_vram_mb()
            if v > self.peak_vram:
                self.peak_vram = v
            time.sleep(self.interval)

    def start(self):
        self.baseline_vram = get_vram_mb()
        self.peak_vram = self.baseline_vram
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        return self.baseline_vram, self.peak_vram

print("="*70, flush=True)
print("TASK T2 - Process A: Faster-Whisper large-v3 on First 10 Minutes", flush=True)
print("="*70, flush=True)

idle_vram = get_vram_mb()
print(f"Pre-process Idle VRAM: {idle_vram} MiB", flush=True)

# 1. FFmpeg audio extraction
print(f"\n1. Extracting first 10 minutes (600s) from {VIDEO_FILE}...", flush=True)
t_ff0 = time.time()
ffmpeg_cmd = [
    "/usr/bin/ffmpeg", "-y",
    "-ss", "00:00:00",
    "-t", "00:10:00",
    "-i", VIDEO_FILE,
    "-vn",
    "-acodec", "pcm_s16le",
    "-ar", "16000",
    "-ac", "1",
    AUDIO_FILE
]
ff_res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
if ff_res.returncode != 0:
    print(f"FFmpeg FAILED: {ff_res.stderr}", flush=True)
    sys.exit(1)

ff_elapsed = time.time() - t_ff0
audio_size = os.path.getsize(AUDIO_FILE)
print(f"Audio extracted in {ff_elapsed:.2f}s: {AUDIO_FILE} ({audio_size:,} bytes / {audio_size/(1024**2):.2f} MB)", flush=True)

# 2. Transcription
sampler = VRAMSampler(interval=0.5)
sampler.start()

print("\n2. Loading WhisperModel('large-v3', device='cuda', compute_type='float16')...", flush=True)
t_load0 = time.time()
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=CACHE_DIR)
load_time = time.time() - t_load0
print(f"Model loaded in {load_time:.2f}s", flush=True)

print("\n3. Running transcription (language='ur', beam_size=5, vad_filter=True, word_timestamps=True)...", flush=True)
t_infer0 = time.time()
segments, info = model.transcribe(
    AUDIO_FILE,
    language="ur",
    beam_size=5,
    vad_filter=True,
    word_timestamps=True,
)

seg_list = []
last_print_time = time.time()
for seg in segments:
    seg_data = {
        "id": seg.id,
        "start": round(seg.start, 2),
        "end": round(seg.end, 2),
        "text": seg.text.strip(),
        "avg_logprob": round(seg.avg_logprob, 3),
        "no_speech_prob": round(seg.no_speech_prob, 3)
    }
    seg_list.append(seg_data)
    if time.time() - last_print_time >= 5.0 or len(seg_list) <= 3:
        print(f"  [{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text.strip()[:60]}...", flush=True)
        last_print_time = time.time()

infer_time = time.time() - t_infer0
rtf = 600.0 / infer_time if infer_time > 0 else 0
print(f"\nTranscription completed in {infer_time:.2f}s (Speed: {rtf:.2f}x real-time)", flush=True)
print(f"Total segments generated: {len(seg_list)}", flush=True)

# Save JSON
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(seg_list, f, ensure_ascii=False, indent=2)
print(f"Saved segments to {OUT_JSON} ({os.path.getsize(OUT_JSON):,} bytes)", flush=True)

# Cleanup model and measure VRAM
del model
import gc
import torch
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
time.sleep(2)

base_vram, peak_vram = sampler.stop()
post_vram = get_vram_mb()

print("\n4. VRAM Summary:", flush=True)
print(f"  Baseline:  {base_vram} MiB", flush=True)
print(f"  Peak:      {peak_vram} MiB (+{peak_vram - base_vram} MiB)", flush=True)
print(f"  Post-Exit: {post_vram} MiB", flush=True)
print(f"  Net Delta: {post_vram - base_vram} MiB", flush=True)
print("="*70, flush=True)
