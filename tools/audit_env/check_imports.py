import sys

modules = [
    "torch",
    "faster_whisper",
    "ctranslate2",
    "sentence_transformers",
    "faiss",
    "networkx",
    "av"
]

print("=== CHECKING PYTHON IMPORTS ===")
all_ok = True
for mod in modules:
    try:
        m = __import__(mod)
        version = getattr(m, "__version__", "unknown")
        print(f"PASS: {mod} (version: {version})")
    except Exception as e:
        print(f"FAIL: {mod} - {e}")
        all_ok = False

if not all_ok:
    sys.exit(1)
print("ALL IMPORTS SUCCESSFUL")
