import os
import sys
import time
import subprocess
import threading
import torch

class VRAMMonitor:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.stop_event = threading.Event()
        self.peak_vram = 0
        self.baseline_vram = self.get_vram()
        self.thread = threading.Thread(target=self._monitor)

    def get_vram(self):
        try:
            out = subprocess.check_output(
                ["/usr/lib/wsl/lib/nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True
            )
            return int(out.strip().split("\n")[0])
        except Exception:
            return 0

    def _monitor(self):
        while not self.stop_event.is_set():
            v = self.get_vram()
            if v > self.peak_vram:
                self.peak_vram = v
            time.sleep(self.interval)

    def start(self):
        self.baseline_vram = self.get_vram()
        self.peak_vram = self.baseline_vram
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        end_vram = self.get_vram()
        return {
            "baseline_mb": self.baseline_vram,
            "peak_mb": self.peak_vram,
            "delta_mb": self.peak_vram - self.baseline_vram,
            "end_mb": end_vram
        }

def test_bge():
    from sentence_transformers import SentenceTransformer

    print("\n==========================================")
    print("6b Check: BAAI/bge-m3 Embedding on CUDA")
    print("==========================================")

    mon = VRAMMonitor()
    mon.start()

    t0 = time.time()
    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    load_time = time.time() - t0
    print(f"BGE-M3 Load time: {load_time:.2f}s")

    test_sentences = [
        "Insightex is a timestamp-grounded knowledge base.",
        "Yeh lecture online vs batch gradient descent ke baray mein hai.",
        "Code-switched Urdu English transcription and semantic search."
    ]

    t1 = time.time()
    embeddings = model.encode(test_sentences, convert_to_tensor=True, show_progress_bar=False)
    infer_time = time.time() - t1
    print(f"Embedding generation time (3 sentences): {infer_time:.2f}s")
    print(f"Embedding shape: {embeddings.shape}")
    print(f"Embedding device: {embeddings.device}")

    del model
    del embeddings
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    time.sleep(1)

    stats = mon.stop()
    print(f"VRAM Baseline: {stats['baseline_mb']} MiB")
    print(f"VRAM Peak:     {stats['peak_mb']} MiB (+{stats['delta_mb']} MiB)")
    print(f"VRAM After:    {stats['end_mb']} MiB")
    print("STATUS: PASS for BGE-M3")

if __name__ == "__main__":
    test_bge()
