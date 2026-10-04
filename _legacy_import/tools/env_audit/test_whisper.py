import os
import sys
import time
import numpy as np

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HOME"] = "E:\\FYP\\cache\\huggingface"

print("Python:", sys.version)

try:
    import ctranslate2
    print(f"ctranslate2 version: {ctranslate2.__version__}")
    print(f"CUDA device count: {ctranslate2.get_cuda_device_count()}")
    print(f"Supported compute types for CUDA: {ctranslate2.get_supported_compute_types('cuda')}")
except Exception as e:
    print(f"ctranslate2 check error: {e}")

try:
    from faster_whisper import WhisperModel
    print("faster_whisper imported successfully.")
except Exception as e:
    print(f"faster_whisper import error: {e}")
    sys.exit(1)

# Generate 10 seconds of 16kHz audio (silence/tone)
sr = 16000
duration = 10
t = np.linspace(0, duration, sr * duration, endpoint=False)
audio = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

for model_name in ["medium", "large-v3"]:
    print(f"\n==========================================")
    print(f"Testing {model_name}...")
    print(f"==========================================")
    for compute_type in ["float16", "int8_float16", "int8"]:
        print(f"\n--- Trying {model_name} with device='cuda', compute_type='{compute_type}' ---")
        t0 = time.time()
        try:
            model = WhisperModel(
                model_name,
                device="cuda",
                compute_type=compute_type,
                download_root="E:\\FYP\\cache\\huggingface\\hub"
            )
            load_time = time.time() - t0
            print(f"Loaded {model_name} ({compute_type}) in {load_time:.2f}s")
            
            t1 = time.time()
            segments, info = model.transcribe(audio, beam_size=1)
            # exhaust generator
            seg_list = list(segments)
            infer_time = time.time() - t1
            print(f"Inference succeeded in {infer_time:.2f}s! Detected language: {info.language} ({info.language_probability:.2f})")
            del model
            print(f"SUCCESS for {model_name} on CUDA with {compute_type}!")
            break
        except Exception as e:
            print(f"Failed with compute_type '{compute_type}': {e}")
