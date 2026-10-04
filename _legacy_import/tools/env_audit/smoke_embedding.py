import os
import time

# Enforce offline mode
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HOME"] = "/mnt/e/FYP/cache/huggingface"

print("--- Testing BAAI/bge-m3 Offline Load ---")
t0 = time.time()
try:
    from sentence_transformers import SentenceTransformer
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Target device: {device}")
    
    # Load model
    model = SentenceTransformer("BAAI/bge-m3", device=device)
    load_time = time.time() - t0
    print(f"Loaded BAAI/bge-m3 successfully in {load_time:.2f}s (Offline mode = True)")
    
    # Dimensions and max seq length
    dim = model.get_sentence_embedding_dimension()
    max_seq = model.max_seq_length
    print(f"Embedding dimension: {dim}")
    print(f"Max sequence length: {max_seq}")

    # Inference test
    sentences = [
        "This is an English test sentence for Urdu-English code switched pipeline.",
        "Yeh ek test sentence hai final year project ke liye."
    ]
    t1 = time.time()
    embeddings = model.encode(sentences)
    infer_time = time.time() - t1
    print(f"Encoded 2 sentences in {infer_time:.4f}s, output shape: {embeddings.shape}")
    print("SUCCESS: BAAI/bge-m3 loaded and executed offline.")
except Exception as e:
    print(f"FAILED to load BAAI/bge-m3: {e}")
    import traceback
    traceback.print_exc()

# Also check Qwen3-Embedding-0.6B presence
print("\n--- Checking Qwen3-Embedding-0.6B on disk ---")
qwen_path = "/mnt/e/FYP/cache/huggingface/hub/models--Qwen--Qwen3-Embedding-0.6B"
if os.path.exists(qwen_path):
    # compute size
    total_size = sum(os.path.getsize(os.path.join(dirpath, f)) for dirpath, _, filenames in os.walk(qwen_path) for f in filenames if not os.path.islink(os.path.join(dirpath, f)))
    print(f"Qwen3-Embedding-0.6B IS PRESENT at {qwen_path} (size on disk: {total_size / (1024*1024):.2f} MB)")
else:
    print(f"Qwen3-Embedding-0.6B NOT found at {qwen_path}")
