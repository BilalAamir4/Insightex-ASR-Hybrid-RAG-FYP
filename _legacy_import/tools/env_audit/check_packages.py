import sys
import platform

print("=== Python Info ===")
print(f"Version: {platform.python_version()}")
print(f"Executable: {sys.executable}")
print(f"Platform: {platform.platform()}")

pkgs = [
    'torch',
    'torchvision',
    'torchaudio',
    'transformers',
    'sentence_transformers',
    'ctranslate2',
    'faster_whisper',
    'faiss',
    'networkx',
    'paddle',
    'paddleocr',
    'cv2',
    'mediapipe',
    'dotenv',
    'pydantic',
    'fastapi',
    'uvicorn',
]

print("\n=== Packages ===")
for p in pkgs:
    try:
        mod = __import__(p)
        ver = getattr(mod, '__version__', 'installed')
        extra = ""
        if p == 'torch':
            cuda_avail = mod.cuda.is_available()
            cuda_ver = getattr(mod.version, 'cuda', 'N/A')
            dev = mod.cuda.get_device_name(0) if cuda_avail else 'N/A'
            extra = f" (CUDA available: {cuda_avail}, CUDA version: {cuda_ver}, Device: {dev})"
        elif p == 'paddle':
            try:
                cuda_comp = mod.device.is_compiled_with_cuda()
                extra = f" (Compiled with CUDA: {cuda_comp})"
            except Exception as e:
                extra = f" (CUDA check error: {e})"
        elif p == 'ctranslate2':
            try:
                cuda_supp = mod.get_cuda_device_count()
                extra = f" (CUDA devices count: {cuda_supp})"
            except Exception as e:
                extra = f" (CUDA check error: {e})"
        print(f"{p}: {ver}{extra}")
    except ImportError as e:
        print(f"{p}: NOT INSTALLED ({e})")
    except Exception as e:
        print(f"{p}: ERROR ({e})")
