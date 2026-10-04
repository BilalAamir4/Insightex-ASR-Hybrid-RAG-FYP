import os
import sys
import time
import numpy as np

print("Python:", sys.version, flush=True)

import ctranslate2
from faster_whisper import WhisperModel

print(f"ctranslate2 version: {ctranslate2.__version__}", flush=True)
print(f"CUDA devices: {ctranslate2.get_cuda_device_count()}", flush=True)
print(f"Supported compute types: {ctranslate2.get_supported_compute_types('cuda')}", flush=True)

models = {
    "medium": r"E:\FYP\cache\huggingface\hub\models--Systran--faster-whisper-medium\snapshots\08e178d48790749d25932bbc082711ddcfdfbc4f",
    "large-v3": r"E:\FYP\cache\huggingface\hub\models--Systran--faster-whisper-large-v3\snapshots\edaa852ec7e145841d8ffdb056a99866b5f0be47"
}

# 3 seconds of silence with tiny noise
audio = (0.01 * np.random.randn(16000 * 3)).astype(np.float32)

for name, path in models.items():
    print(f"\n==========================================", flush=True)
    print(f"Testing {name} from direct snapshot path: {path}", flush=True)
    print(f"Path exists: {os.path.exists(path)}", flush=True)
    
    for compute_type in ["float16", "int8_float16"]:
        print(f"Trying compute_type='{compute_type}'...", flush=True)
        t0 = time.time()
        try:
            model = WhisperModel(path, device="cuda", compute_type=compute_type, local_files_only=True)
            load_time = time.time() - t0
            print(f"Loaded {name} ({compute_type}) in {load_time:.2f}s", flush=True)
            
            t1 = time.time()
            segments, info = model.transcribe(audio, beam_size=1, temperature=0.0, without_timestamps=True)
            # read one segment
            for s in segments:
                print(f"Segment: {s.text}", flush=True)
                break
            infer_time = time.time() - t1
            print(f"Inference succeeded in {infer_time:.2f}s! Lang: {info.language}", flush=True)
            del model
            print(f"SUCCESS: {name} works on CUDA with {compute_type}!", flush=True)
            break
        except Exception as e:
            print(f"Failed with {compute_type}: {e}", flush=True)
