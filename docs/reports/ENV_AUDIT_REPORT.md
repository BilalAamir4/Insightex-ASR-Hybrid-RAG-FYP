# Insightex: Development Environment Audit & State Verification Report

**Date:** 3 October 2026  
**Auditor:** Antigravity Pair-Programming Agent  
**Project:** Final-Year Project — "Insightex" (Timestamp-Grounded Knowledge Base for Code-Switched Lecture Videos)  
**Host Machine:** Windows 11 Host (Build 26100), WSL2 (`Ubuntu-24.04`), Intel Core i7 (20 threads), 32 GB RAM, NVIDIA GeForce RTX 3070 (8 GB VRAM, Driver 616.64, CUDA 13.4 UMD)  
**Disk Image Location:** WSL2 ext4 VHDX resides at `E:\FYP\wsl\Ubuntu-24.04\ext4.vhdx` (Drive E: policy fully compliant)  
**Audit Notice:** Rows marked VERIFIED were re-checked in the sessions of 3 October 2026; rows marked CARRIED OVER were not.

---

## 1. Component Summary Table

| Component | Runtime Environment | Version / Format | Verified this session? | Loads Offline? | Idle VRAM | Peak VRAM | Status | One-Line Note |
|---|---|---|---|---|---|---|---|---|
| **FFmpeg / ffprobe (Linux native)** | WSL2 Ubuntu-24.04 (`/usr/bin/ffmpeg`) | 6.1.1-3ubuntu5 | **VERIFIED** | N/A (binary) | N/A | N/A | **READY** | Native package installed; extracted 10-min 16 kHz mono WAV from `lecture_test.mp4` in 3.24s. |
| **FFmpeg / ffprobe (Windows)** | Windows host (`E:\Uni Softwares\FFMPEG\bin\`) | 8.1.2-essentials (gyan.dev) | **VERIFIED** | N/A (binary) | N/A | N/A | **READY** | Retained for host tasks; full NVENC, libx264, AAC support. |
| **faster-whisper (Weights)** | WSL ext4 (`~/cache/huggingface/hub/`) & `E:\FYP\cache\` | `medium` (1.43 GB / 1,530 MB), `large-v3` (2.88 GB / 3,092 MB) | **VERIFIED** | **YES** | N/A | N/A | **READY** | Bit-for-bit SHA256 match: 0 mismatches. Earlier 2,919/5,895 MB figures were exactly 2.00x binary MiB due to counting both blobs and snapshot symlinks. |
| **faster-whisper / CTranslate2 (Runtime)** | WSL2 venv (`~/envs/insightex`) | `faster-whisper 1.2.1`, `ctranslate2 4.8.2`, `av 14.1.0` | **VERIFIED** | **YES** | 1,006 MiB | 5,530 MiB (large-v3) | **READY** | CUDA float16 verified; 10-min lecture transcribed in 66.69s (9.00x real time). VRAM returns cleanly to baseline. Requires `run_in_env.sh`. |
| **Ollama Service & LLM** | Windows Host Service (`127.0.0.1:11434`) | Ollama 0.33.3, Qwen3.5 9.7B Q4_K_M (6.6 GB) | **VERIFIED** | **YES** | 1,002 MiB | 7,566 MiB (92.4% of 8192 MiB) | **READY** | Model digest `6488c96fa5fa` verified constant. Bound strictly to `127.0.0.1:11434`. 100% GPU offload at num_ctx 8192 in `ollama ps`. |
| **Embedding Model (BAAI/bge-m3)** | WSL2 venv (`~/envs/insightex`) | 568M params, 1024-d, 8192 seq (4.25 GB blobs) | **VERIFIED (Cache only)** | Measured in earlier session, not re-run (2 Oct 2026) | Measured in earlier session, not re-run (2 Oct 2026) | Measured in earlier session, not re-run (2 Oct 2026) | **READY** | Cache integrity SHA256 verified (0 mismatches across all blobs). SentenceTransformer loads offline on CUDA; warm load 1.70s on ext4. |
| **FAISS** | WSL2 venv (`~/envs/insightex`) | `faiss-cpu 1.15.1` | **CARRIED OVER** | N/A | N/A | CPU only | **READY** | Carried over from the first audit, not re-verified this session. |
| **NetworkX** | WSL2 venv (`~/envs/insightex`) | 3.6.1 | **CARRIED OVER** | N/A | N/A | CPU only | **READY** | Carried over from the first audit, not re-verified this session. |
| **Python Environment** | WSL2 venv (`~/envs/insightex`) | Python 3.12, `torch 2.11.0+cu128`, `jsonschema 4.26.0` | **VERIFIED** | N/A | N/A | N/A | **READY** | Virtual environment on ext4 with pinned `requirements.lock.txt`. Requires `run_in_env.sh` for CUDA shared libraries during model compute. |
| **PaddleOCR / PaddlePaddle** | WSL2 venv (`~/envs/paddleocr-vl`) | `paddlepaddle-gpu 3.2.1`, `paddleocr 3.7.0` | **CARRIED OVER** | Partial | 1,850 MiB | ~7,950 MiB (reserved) | **STANDBY** | Carried over from the first audit, not re-verified this session. Out of scope for initial ASR-first pipeline. |
| **Docker Engine** | Windows Host / WSL2 integration | Client 29.8.0, Engine stopped | **CARRIED OVER** | N/A | N/A | N/A | **STANDBY** | Carried over from the first audit, not re-verified this session. VHDX relocated to `E:\FYP\docker\DockerDesktopWSL`. |

---

## 2. Review of Architectural & Configuration Decisions

Every proposed fix from the audit history is classified below:

| Decision / Proposal | Status | Technical Rationale & Current State |
|---|---|---|
| **1. Set `OLLAMA_MODELS` to `E:\FYP\LLMs`** | **DONE** | Environment variable configured on Windows User Registry. Verified with `ollama list`: detects `qwen3.5:latest` (6.6 GB). |
| **2. Set `OLLAMA_HOST=0.0.0.0`** | **REJECTED** | **Security Hazard:** Exposing port 11434 on all network interfaces allows any host on local Wi-Fi to submit unauthenticated inference. Host remains bound to `127.0.0.1`. |
| **3. Export gateway IP in `~/.bashrc` (`OLLAMA_HOST`)** | **SUPERSEDED** | Superseded by WSL2 mirrored networking (`networkingMode=mirrored` in `%UserProfile%\.wslconfig`). WSL2 accesses Windows Ollama at `localhost:11434` without dynamic IP resolution. |
| **4. Symlink WSL caches into `/mnt/e/FYP/cache`** | **REJECTED** | **Severe I/O Latency:** DrvFS cross-filesystem overhead causes 3.5x–4.4x slower cold loads and 4.3x–7.4x slower warm loads. Master cache preserved on `E:\FYP\cache`, runtime cache stored on ext4 (`~/cache`). |
| **5. Install native Linux FFmpeg in WSL2** | **DONE** | Installed `ffmpeg 6.1.1-3ubuntu5` via APT. Audio extraction executes locally in WSL without host interop latency. |
| **6. Consolidate Python Environments into `~/envs/insightex`** | **DONE** | Unified venv on ext4 with `torch 2.11.0+cu128`, `faster-whisper 1.2.1`, `ctranslate2 4.8.2`, `sentence-transformers 6.1.0`, `faiss-cpu 1.15.1`, `networkx 3.6.1`, and `jsonschema 4.26.0`. Pinned in `requirements.lock.txt`. |
| **7. Remove Empty Directory `E:\LLMs`** | **DONE** | Verified only empty structure existed; removed. |
| **8. Environment Configuration Script (`insightex_env.sh`)** | **DONE** | Configured with `HF_HOME`, `HF_HUB_OFFLINE=1`, `PIP_CACHE_DIR`, `TORCH_HOME`, `OLLAMA_BASE_URL`, and idempotency guard for `LD_LIBRARY_PATH`. Sourced via `run_in_env.sh`. |

---

## 3. Sequential VRAM Dynamics & Architecture Contract

### 3.1 Empirical VRAM Measurements per Stage
All measurements were taken via background polling of `/usr/lib/wsl/lib/nvidia-smi` and Windows host `nvidia-smi`:

| Stage / Component | Pre-Launch Idle VRAM | Peak VRAM | Peak % of 8192 MiB | Net Delta | Available Headroom | Post-Exit VRAM | Clean Release? |
|---|---|---|---|---|---|---|---|
| **System Idle Baseline** | 994 – 1,167 MiB | N/A | N/A | N/A | 7,025 – 7,198 MiB | 994 – 1,167 MiB | Baseline (Windows Desktop & IDE) |
| **Whisper medium (CUDA float16, 30s clip)** | 1,007 MiB | 4,026 MiB | 49.15% | +3,019 MiB | 4,166 MiB | 1,007 MiB | **YES** (Subprocess exit returns to baseline) |
| **Whisper large-v3 (CUDA float16, 10 min)** | 1,006 MiB | 5,530 MiB | 67.51% | +4,524 MiB | 2,662 MiB | 1,006 MiB | **YES** (Subprocess exit returns to baseline) |
| **BAAI/bge-m3 (SentenceTransformer CUDA)** | 748 MiB | 3,089 MiB | 37.71% | +2,341 MiB | 5,103 MiB | 748 MiB | **YES** (Measured 2 Oct 2026, not re-run) |
| **Ollama Qwen3.5 (C3: num_ctx 4096)** | 1,002 MiB | 7,426 MiB | 90.65% | +6,424 MiB | 766 MiB | 1,002 MiB | **YES** (`unload_model()` with `keep_alive: 0`) |
| **Ollama Qwen3.5 (C2: num_ctx 8192)** | 1,002 MiB | 7,566 MiB | 92.36% | +6,564 MiB | 626 MiB | 1,002 MiB | **YES** (`unload_model()` with `keep_alive: 0`) |

### 3.2 VRAM Headroom & Desktop Sharing
- **Desktop Memory Sharing:** The 8192 MiB VRAM pool is shared with Windows desktop applications (Antigravity IDE, Claude Desktop, Edge WebView2, Explorer, Wallpaper Engine). Across observed sessions, the idle baseline varied between **994 MiB and 1,167 MiB**.
- **Available Headroom:** Headroom is strictly calculated as `8192 MiB - Peak_VRAM`. Under configuration C2 (`num_ctx 8192`), peak VRAM was **7,566 MiB**, leaving exactly **626 MiB of headroom** (not 466 MiB, which derived from an older 7,726 MiB peak).
- **VRAM Gap Analysis:** `ollama ps` reports a model allocation of **5.6 GB** (~5,600 MiB), while host `nvidia-smi` delta over idle was **6,564 MiB** (a gap of ~964 MiB). Under Windows WDDM, `nvidia-smi --query-compute-apps` reports `[N/A]` for per-process memory across all compute and graphics applications. The gap reflects KV context cache, CUDA runtime libraries, and WDDM memory management. Because individual process memory cannot be isolated by the driver query tools without admin rights, the exact decomposition is reported as **gap cause not tested**.

### 3.3 Non-Negotiable Architecture Contract
1. **Zero Concurrent CUDA Stages:** Whisper (CTranslate2) and BGE-M3 (PyTorch) allocate persistent device pools. Because Ollama Qwen3.5 peaks at **7,566 MiB** (leaving only 626 MiB of headroom on an 8 GB card), running Whisper and Ollama concurrently will trigger an immediate CUDA Out-of-Memory failure.
2. **Subprocess Isolation:** Each pipeline stage (FFmpeg audio prep, Whisper transcription, Ollama concept extraction, BGE-M3 embedding) must execute as an independent process that fully exits before the next stage starts.
3. **Ollama Batch Lifecycle:** During a multi-chunk extraction batch, Ollama must be called with `"keep_alive": "10m"` to prevent reloading the model on every chunk. At the conclusion of the batch, the runner must invoke `unload_model()` with `"keep_alive": 0` in a `finally` block and poll until `ollama ps` confirms the model is unmapped.

---

## 4. Model Load Latency Benchmarks (ext4 vs. DrvFS)

Measurements taken with cache flushes (`sync; echo 3 > /proc/sys/vm/drop_caches`) for cold runs, followed immediately by warm loads:

| Model | Filesystem Location | Cold Load (s) | Warm Load (s) | Warm vs Cold Speedup (Within FS) | Peak VRAM |
|---|---|---|---|---|---|
| **whisper-medium** | ext4 (`~/cache/huggingface/hub`) | **3.76 s** | **0.66 s** | **5.70x** | 3,112 MiB |
| **whisper-medium** | DrvFS (`/mnt/e/FYP/cache/...`) | 16.51 s | 4.90 s | 3.37x | 3,112 MiB |
| **whisper-large-v3** | ext4 (`~/cache/huggingface/hub`) | **8.37 s** | **2.03 s** | **4.12x** | 4,936 MiB |
| **whisper-large-v3** | DrvFS (`/mnt/e/FYP/cache/...`) | 29.64 s | 8.64 s | 3.43x | 4,645 MiB |
| **bge-m3** | ext4 (`~/cache/huggingface/hub`) | *6.25 s* | *1.70 s* | *3.68x* | 3,089 MiB |
| **bge-m3** | DrvFS (`/mnt/e/FYP/cache/...`) | *27.50 s* | *10.26 s* | *2.68x* | 3,089 MiB |

*(Note: bge-m3 load times measured in earlier session on 2 October 2026, not re-run this session).*

### Load Speedup Summary Derived Directly from Table
- **Cold load speedup (ext4 vs DrvFS):**
  - `whisper-medium`: 16.51 s / 3.76 s = **4.39x faster on ext4**
  - `whisper-large-v3`: 29.64 s / 8.37 s = **3.54x faster on ext4**
  - `bge-m3`: 27.50 s / 6.25 s = **4.40x faster on ext4**
  - **Cold speedup range:** **3.5x to 4.4x faster on ext4**.
- **Warm load speedup (ext4 vs DrvFS):**
  - `whisper-medium`: 4.90 s / 0.66 s = **7.42x faster on ext4**
  - `whisper-large-v3`: 8.64 s / 2.03 s = **4.26x faster on ext4**
  - `bge-m3`: 10.26 s / 1.70 s = **6.04x faster on ext4**
  - **Warm speedup range:** **4.3x to 7.4x faster on ext4**.
- **NTFS Cache Note:** The DrvFS cold benchmark was performed by dropping the Linux page cache inside WSL2 (`drop_caches`), which does **not** flush the underlying Windows host NTFS disk cache. Therefore, the actual DrvFS cold penalty from a cold NTFS disk state may be larger than measured here.

---

## 5. Whisper Audio Verification & Speed Benchmark (Task T3 & F3 Recomputation)

Benchmarks were executed on a real 30.0-second Urdu/English code-switched lecture segment (`clip_30s.wav`, 16 kHz mono WAV) with settings: `language="ur"`, `beam_size=5`, `vad_filter=True`, `word_timestamps=True`, `compute_type="float16"`, `device="cuda"`.

### 5.1 Recomputed Empirical Data Table (All Derived Figures Script-Verified)

| Test Condition | Cold (Run 1) | Warm Runs (Runs 2 to 5) | Warm Median (statistics.median) | Warm Min / Max | Warm Mean | Speed Factor (30.0 / median) | RTF (median / 30.0) |
|---|---|---|---|---|---|---|---|
| **Order 1: large-v3** | 4.40 s | [3.37 s, 3.36 s, 3.37 s, 3.33 s] | **3.365 s** | 3.33 s / 3.37 s | 3.357 s | **8.92x real time** | **0.1122** |
| **Order 1: medium** | 7.75 s | [10.68 s, 9.45 s, 13.46 s, 11.49 s] | **11.085 s** | 9.45 s / 13.46 s | 11.270 s | **2.71x real time** | **0.3695** |
| **Order 2: medium** | 7.67 s | [5.74 s, 7.66 s, 4.39 s, 18.14 s] | **6.700 s** | 4.39 s / 18.14 s | 8.982 s | **4.48x real time** | **0.2233** |
| **Order 2: large-v3** | 3.70 s | [3.39 s, 2.68 s, 3.34 s, 3.33 s] | **3.335 s** | 2.68 s / 3.39 s | 3.185 s | **9.00x real time** | **0.1112** |
| **Extra: medium (`temp=0.0`)** | 3.46 s | [3.53 s, 3.55 s, 3.53 s, 3.45 s] | **3.530 s** | 3.45 s / 3.55 s | 3.515 s | **8.50x real time** | **0.1177** |

### 5.2 Per-Segment Quality Metrics & Transcription Differences (Task F3d)
In Task F3d, fresh isolated subprocesses logged per-segment parameters (`avg_logprob`, `compression_ratio`, `temperature`):

| Condition | Run Type | Segments | Mean avg_logprob | Min avg_logprob | Max compression_ratio |
|---|---|---|---|---|---|
| **medium (default settings)** | Cold (Run 1) | 4 | -0.2323 | -0.2323 | 2.3984 |
| **medium (default settings)** | Warm (Run 2) | 7 | -0.7229 | -0.7229 | 2.1056 |
| **medium (`temperature=0.0`)** | Cold (Run 1) | 12 | -0.2774 | -0.2784 | 2.4144 |
| **medium (`temperature=0.0`)** | Warm (Run 2) | 12 | -0.2774 | -0.2784 | 2.4144 |
| **large-v3 (default)** | Cold (Run 1) | 18 | -0.1082 | -0.1499 | 2.1582 |
| **large-v3 (default)** | Warm (Run 2) | 18 | -0.1082 | -0.1499 | 2.1582 |

### 5.3 Empirical Observations
1. **Fallback Loop Impact on `medium`:** Across both Run Order 1 and Run Order 2, `faster-whisper medium` with default settings triggered the automatic temperature-fallback loop on 4 out of 5 runs (max temperature reaching 0.8 and 1.0), causing repeated multi-pass decoding and high runtime variability (4.39 s to 18.14 s).
2. **Effect of Disabling Fallback (`temp=0.0`):** On this clip, disabling the temperature fallback removed the extra decoding passes and the run-time variance (cause tested by the `temp=0.0` run), yielding a stable warm median of **3.530 s** (**8.50x real time**, RTF 0.1177).
3. **Text Comparison (medium default vs medium temp=0.0):** In the warm run, medium-default produced 7 segments and retained English technical terms in Latin script (`machine learning`, `softwareات`, `server`), whereas medium-temp0 produced 12 segments and transliterated those same terms phonetically into Urdu script (`ماشین لرننگ`, `سوٹ ویس`, `سرور`). 5 out of 5 matched start-time segments exhibited textual differences.
4. **Behavior of `large-v3`:** In both run orders, `large-v3` completed all runs at temperature 0.0 without triggering any temperature fallback retries, achieving **3.335 s – 3.365 s warm median** (**8.92x – 9.00x real time**, RTF ~0.111–0.112).
5. **Scope of Claim:** These measurements describe the exact data recorded for `clip_30s.wav`. No general claim of equality or superiority is made. Checkpoint selection requires a comprehensive WER evaluation across the full lecture corpus.

---

## 6. Ollama Batch Contract & Verification (Task T2 & F2/F5 Re-check)

### 6.1 Model Identity & Verification
- **Model Name:** `qwen3.5:latest`
- **Short Model ID (`ollama list`):** `6488c96fa5fa`
- **Full Manifest Digest:** `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7` (LastWriteTime: `2026-10-02 16:18:49`, size: 709 bytes)
- **Model Weights Blob Digest:** `sha256:dec52a44569a2a25341c4e4d3fee25846eed4f6f0b936278e3a3c900bb99d37c` (LastWriteTime: `2026-10-01 00:48:20`, size: 6,594,462,816 bytes)
- **Identity Outcome:** The model ID `6488c96fa5fa` has been verified as constant across all raw logs on disk. Zero scripts called pull/create/cp/delete (0 matches).

### 6.2 Hypotheses Resolution
- **H1 (keep_alive):** Supported indirectly by the 8.7 s load_duration observed on cold loads after each unload; no run used `keep_alive: 0` on every call. Keeping `keep_alive: "10m"` during the batch reduced per-chunk load duration to 0.00 s. Calling `unload_model()` with `keep_alive: 0` at the end of the batch in a `finally` block cleanly returned VRAM to baseline within 2.5 seconds.
- **H2 (Schema vs format="json"):** Not distinguishable: both formats passed 10/10 on this data. However, the JSON Schema object guarantees field compliance (`name`, `description`, `exam_relevant`) and enforces `additionalProperties: false` natively at the engine level.
- **H3 (GPU Offload at 8192 context):** `ollama ps` showed **100% GPU** (5.6 GB VRAM, CONTEXT 8192); log evidence: none. The earlier claim quoting "offload to cuda: 100% (36/36 layers offloaded to GPU)" from `server.log` was unsupported by the log files and is formally retracted.

### 6.3 Reproducibility Verification (Task F2 Re-Run on Identified Chunks)
In Task F2, 3 chunks were selected by exact audio start time and evaluated across 3 independent runs under C2 (JSON Schema, `num_ctx: 8192`, `temperature: 0.1`):

- **Chunk 02 [61.34s -> 121.38s]:**
  - Set equality across 3 runs: **True**
  - Concept names: `['Production Environment', 'Development Environment', 'Batch Learning (Offline Learning)', 'Online Learning']`
  - Pairwise Jaccards: R1-R2 = 1.0000, R2-R3 = 1.0000, R1-R3 = 1.0000 | **Mean Jaccard = 1.0000**
- **Chunk 05 [243.32s -> 304.06s]:**
  - Set equality across 3 runs: **False**
  - Run 1 concepts: `['Static Machine Learning Model', 'Online Learning (Implied)', 'Recommendation Engine']`
  - Run 2 concepts: `['Static Machine Learning Model', 'Evolving Business Scenario', 'Recommendation Engine', 'Server-Side Deployment']`
  - Run 3 concepts: `['Static Machine Learning Model', 'Evolving Business Scenario', 'Recommendation Engine', 'Online Learning']`
  - Pairwise Jaccards: R1-R2 = 0.4000, R2-R3 = 0.6000, R1-R3 = 0.4000 | **Mean Jaccard = 0.4667**
- **Chunk 08 [426.16s -> 487.50s]:**
  - Set equality across 3 runs: **False**
  - Run 1 & 2 concepts: `['Batch Learning', 'Online Learning', 'Data Scaling Challenges']`
  - Run 3 concepts: `['Batch Learning', 'Online Learning', 'Data Scaling Challenges', 'Periodic Retraining']`
  - Pairwise Jaccards: R1-R2 = 1.0000, R2-R3 = 0.7500, R1-R3 = 0.7500 | **Mean Jaccard = 0.8333**

### 6.4 Provisional Status Notice
Concept extraction quality and suitability for Insightex knowledge graph construction have **not** been evaluated by the agent and remain **provisional** until human review of the transcribed audio and extracted concept samples.

### 6.5 Recommended Pipeline Request Body & Unload Contract

#### Batch Inference Request:
```json
{
  "endpoint": "/api/chat",
  "method": "POST",
  "url": "http://localhost:11434/api/chat",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "model": "qwen3.5:latest",
    "messages": [
      {
        "role": "system",
        "content": "You are an expert AI educator analyzing bilingual lecture transcripts. Return ONLY a valid JSON object matching the requested schema."
      },
      {
        "role": "user",
        "content": "<PROMPT_AND_TRANSCRIPT_CHUNK>"
      }
    ],
    "stream": false,
    "think": false,
    "keep_alive": "10m",
    "format": {
      "type": "object",
      "properties": {
        "concepts": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "description": {"type": "string"},
              "exam_relevant": {"type": "boolean"}
            },
            "required": ["name", "description", "exam_relevant"],
            "additionalProperties": false
          }
        }
      },
      "required": ["concepts"],
      "additionalProperties": false
    },
    "options": {
      "num_ctx": 8192,
      "temperature": 0.1,
      "num_predict": 600
    }
  }
}
```
*Note on `num_predict`:* The maximum observed `eval_count` across all chunk runs was 400 tokens. Setting `num_predict: 600` provides a 50% margin while capping runaway generation.

#### Batch Unload Contract (Execute in `finally` block):
```python
def unload_model():
    """Unload model from VRAM and poll ollama ps until clean."""
    requests.post("http://localhost:11434/api/chat", json={"model": "qwen3.5:latest", "keep_alive": 0})
    for _ in range(30):
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
        if "qwen3.5:latest" not in res.stdout:
            break
        time.sleep(1)
```

---

## 7. Execution Architecture: Launcher Rule & Offline Protocol

### 7.1 Mandatory Launcher Rule (`run_in_env.sh`)
All Insightex pipeline stages must be launched through the environment wrapper:
```bash
bash /mnt/e/FYP/tools/env_audit/run_in_env.sh <command>
```

#### Empirical Failure Mode Without Wrapper (Task F6):
Executing Python commands from a non-login, non-interactive shell (`wsl -d Ubuntu-24.04 bash ...`) without the wrapper demonstrated the following distinct behaviors:
1. `/home/bilal_aamir/envs/insightex/bin/python -c "import ctranslate2"` $\rightarrow$ **Succeeds (Exit code 0).**
2. `/home/bilal_aamir/envs/insightex/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` $\rightarrow$ **Succeeds (Exit code 0, prints 1).**
3. `WhisperModel("medium", device="cuda").transcribe(...)` $\rightarrow$ **Fails with raw exception:**
   ```
   RuntimeError: Library libcublas.so.12 is not found or cannot be loaded
   ```
   *Critical Diagnosis:* `import ctranslate2` and CUDA device queries do NOT trigger the missing library error; the failure occurs strictly during actual model tensor execution (`model.encode(features)`).
4. Running with system python (`wsl -d Ubuntu-24.04 python3 -c "import ctranslate2"`) fails with `ModuleNotFoundError: No module named 'ctranslate2'` because `/usr/bin/python3` does not have project dependencies installed.

When launched via `run_in_env.sh`, `LD_LIBRARY_PATH` is dynamically populated with all 16 CUDA library directories from the `nvidia-*` virtual environment packages, and full GPU transcription succeeds cleanly.

### 7.2 Strict Offline Protocol (`HF_HUB_OFFLINE=1`)
`HF_HUB_OFFLINE=1` is enforced globally across all project shells to eliminate network calls and prevent accidental weight downloads during pipeline runs.

To add a new HuggingFace model safely without altering global settings:
1. Run a single download command explicitly overriding the offline flag:
   ```bash
   HF_HUB_OFFLINE=0 HF_HOME=/mnt/e/FYP/cache/huggingface python3 -c "from huggingface_hub import snapshot_download; snapshot_download('<REPO_ID>')"
   ```
2. Copy the downloaded repository from the master cache to the runtime cache:
   ```bash
   cp -ru /mnt/e/FYP/cache/huggingface/hub/models--<MODEL_NAME> /home/bilal_aamir/cache/huggingface/hub/
   ```
3. Run the Task T1 / F7 hash verification script (`run_F7_check.py`) to confirm zero SHA256 mismatches between master and ext4.

---

## 8. Shell and System History Verification (Task T4 Audit)

- **Task T4 Result: PARTIAL** (fsutil required administrator privileges and was not run; pre-edit full `.bashrc` was not recoverable).
- **`~/.bashrc` Editing History:** Inspection of `~/.bash_history`, `~/.profile`, and session transcripts shows earlier commands added DrvFS cache exports (`/mnt/e/FYP/cache/huggingface`), which were subsequently cleaned up. Full pre-edit `.bashrc` not recoverable; lost lines not verified beyond the removed cache exports.
- **`%UserProfile%\.wslconfig` Timestamps:** CreationTime: `10/3/2026 12:33:02 PM`, LastWriteTime: `10/3/2026 12:33:02 PM`. Overwriting an existing file in Windows can preserve original file CreationTime. Prior existence of `.wslconfig` is not verified.
- **Filesystem Integrity Checks:**
  - WSL `dmesg | grep -iE "error|ext4|corrupt|I/O|recover|orphan"`: No ext4 or I/O corruption errors observed in the output.
  - WSL `journalctl -b -p warning`: 3 log lines returned (`init` missing mount, `systemd-sysctl` netfilter warnings). No storage errors.
  - Windows `Get-Volume -DriveLetter E`: Status `Healthy`, OperationalStatus `OK`.
  - Windows `fsutil dirty query E:`: Returned `Error 5: Access is denied` (needs admin, not run).
  - Summary: No errors observed in the output above.

---

## 9. Appendix: Corrections to the Previous Report

| Item / Claim | Old Value | Corrected Value | Reason for Correction |
|---|---|---|---|
| **Peak VRAM % (C2 ctx 8192)** | 94.6% | **92.36% (92.4%)** | 7,566 MiB / 8192 MiB is 92.36%. Old 94.6% came from older 7,726 MiB peak. |
| **Peak VRAM % (C3 ctx 4096)** | Not reported | **90.65% (90.6%)** | 7,426 MiB / 8192 MiB is 90.65%. |
| **Available Headroom (C2)** | ~466 MiB | **626 MiB** | 8192 MiB - 7,566 MiB = 626 MiB. Old 466 MiB came from 8192 - 7726 MiB. |
| **Available Headroom (C3)** | Not reported | **766 MiB** | 8192 MiB - 7,426 MiB = 766 MiB. |
| **Whisper Warm Medians (T3)** | Order 1 med: 11.09s; Order 2 med: 6.70s; large-v3: 3.37s / 3.33s | **Order 1 med: 11.085s; Order 2 med: 6.700s; large-v3: 3.365s / 3.335s** | Recomputed with `statistics.median` on 4 warm runs (mean of middle two values). |
| **Whisper Speed Factor (Order 2 medium)** | 4.58x real time | **4.48x real time** | 30.0 s / 6.700 s = 4.4776x real time. |
| **bge-m3 Load Times** | Listed as verified this session | **Relabeled: measured in earlier session, not re-run (2 Oct 2026)** | Only cache hashing was re-run this session; load benchmark was carried over. |
| **Cache Size Discrepancy** | "doubled" (generic) | **Exactly 2.00x binary MiB (1.91x decimal MB)** | Medium: 2919 MB / 1459.41 MiB = 2.0001x; Large: 5895 MB / 2948.47 MiB = 1.9993x. Caused by counting both blobs and snapshot symlinks. |
| **GPU Offload Log Quote (H3)** | "offload to cuda: 100% (36/36 layers offloaded to GPU)" | **Quoted line retracted; log evidence: none** | Log search confirmed quote was not in any log file. Retracted per Task F5. |
| **Launcher Failure Mode** | "import ctranslate2 fails" | **Fails at model.encode(features); import succeeds** | Empirical test proved import passes; error triggers only during actual CUDA tensor execution. |
| **Chunk Reproducibility Jaccard** | Chunk 5 Jaccard: 0.556 | **Re-run Mean Jaccard: 0.4667 (Chunk 2: 1.0000, Chunk 8: 0.8333)** | Previous chat text contained fabricated concept sets. Script calculation now verified. |
| **Model ID qwen3.5:latest** | b896b1b46a78 (in previous chat text) | **6488c96fa5fa (constant across all raw logs)** | Raw disk logs never had b896b1b46a78; it was a chat typo. |

---

## 10. Final Verdict

1. **Ready for Module 1 transcription work (ffmpeg -> Whisper): YES**  
   *Justification:* Verified on hardware. Full 10-minute extraction from `lecture_test.mp4` completed in 3.24s via native FFmpeg, and `faster-whisper large-v3` transcribed all 307 segments in 66.69s (9.00x real time, peak VRAM 5,530 MiB). Process exit cleanly returned GPU VRAM to the 1,006 MiB baseline. Zero hash mismatches across master and ext4 model weights.

2. **Ready for Module 1 concept extraction (Ollama contract): YES (provisional on transcript review)**  
   *Justification:* Verified on hardware. Ollama `qwen3.5:latest` (digest `6488c96fa5fa`) is locked to loopback `127.0.0.1:11434`, operates at 100% GPU offload (peak VRAM 7,566 MiB, 92.4% utilization, 626 MiB headroom) with num_ctx 8192, and achieved 100% JSON schema validity across all 10 real lecture transcript chunks. Adopting `keep_alive: "10m"` during batches eliminated the ~8.8s reload penalty per chunk. Memory unloads cleanly to baseline upon batch completion. Concept extraction quality remains provisional pending human inspection of extracted concepts.
