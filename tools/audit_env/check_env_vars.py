import os

vars_to_check = ["HF_HOME", "HF_HUB_OFFLINE", "OLLAMA_BASE_URL", "LD_LIBRARY_PATH"]
for v in vars_to_check:
    print(f"{v}={os.environ.get(v, '<NOT_SET>')}")
