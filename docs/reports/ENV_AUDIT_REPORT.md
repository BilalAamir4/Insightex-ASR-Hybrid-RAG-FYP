# Insightex: Development Environment State Report

**Measurements dated:** 2 and 3 October 2026. **Rewritten:** 4 October 2026 as a single current-state document for the repository migration (superseded findings and rejected fixes removed; the original is in git tag `import-baseline` at `_legacy_import/tools/env_audit/ENV_AUDIT_REPORT.md`).
**Project:** Insightex, timestamp-grounded knowledge base for code-switched lecture videos.
**Host:** Windows 11, WSL2 `Ubuntu-24.04`, Intel Core i7 (20 threads), 32 GB RAM, NVIDIA GeForce RTX 3070 (8 GB VRAM, driver 616.64, CUDA 13.4 UMD). WSL ext4 disk: `E:\FYP\wsl\Ubuntu-24.04\ext4.vhdx`.
**Labels:** VERIFIED = re-checked on 3 October 2026. CARRIED OVER = measured in an earlier session and not re-run. UNVERIFIED = stated but not checked. No measurement in this document was re-run during the migration; paths refer to the layout after migration (`~/insightex`, `~/insightex-data`).

---

## 1. Component summary

| Component | Runtime | Version / format | Status label | Idle VRAM | Peak VRAM | Note |
|---|---|---|---|---|---|---|
| FFmpeg / ffprobe (Linux) | WSL2 (`/usr/bin/ffmpeg`) | 6.1.1-3ubuntu5 | VERIFIED | n/a | n/a | Extracted a 10-minute 16 kHz mono WAV in 3.24 s. |
| FFmpeg / ffprobe (Windows) | Windows host | 8.1.2-essentials (gyan.dev) | VERIFIED | n/a | n/a | For host tasks. |
| faster-whisper weights | `~/cache/huggingface/hub/` and `E:\FYP\cache\` | `medium` (1.43 GB), `large-v3` (2.88 GB) | VERIFIED | n/a | n/a | SHA256 match between master and ext4, 0 mismatches. Cache sizes are exactly 2.00x if blobs and snapshot symlinks are both counted. |
| faster-whisper / CTranslate2 | `~/envs/insightex` | faster-whisper 1.2.1, ctranslate2 4.8.2, av 14.1.0 | VERIFIED | 1,006 MiB | 5,530 MiB (large-v3, 10 min) | CUDA fp16; 10-minute lecture in 66.69 s (9.00x real time). Needs the wrapper. |
| Ollama and LLM | Windows host service, `127.0.0.1:11434` | Ollama 0.33.3, qwen3.5 9.7B Q4_K_M | VERIFIED | 1,002 MiB | 7,566 MiB (92.4%) | Digest `6488c96fa5fa`; 100% GPU offload in `ollama ps` at `num_ctx` 8192. |
| BAAI/bge-m3 | `~/envs/insightex` | 568M params, 1024-d, 8192 seq (4.25 GB) | VERIFIED (cache hashes) / CARRIED OVER (load, VRAM; 2 Oct) | 748 MiB | 3,089 MiB | Loads offline on CUDA; warm load 1.70 s on ext4. |
| FAISS | `~/envs/insightex` | faiss-cpu 1.15.1 | CARRIED OVER | n/a | CPU only | |
| NetworkX | `~/envs/insightex` | 3.6.1 | CARRIED OVER | n/a | CPU only | |
| Python environment | `~/envs/insightex` | Python 3.12, torch 2.11.0+cu128, jsonschema 4.26.0 | VERIFIED | n/a | n/a | Pinned in `requirements.lock.txt`. |
| PaddleOCR / PaddlePaddle | `~/envs/paddleocr-vl` | paddlepaddle-gpu 3.2.1, paddleocr 3.7.0 | CARRIED OVER | 1,850 MiB | about 7,950 MiB (reserved) | Optional; out of scope for the ASR-first baseline. |
| Docker | Windows host | Client 29.8.0, engine stopped | CARRIED OVER | n/a | n/a | VHDX at `E:\FYP\docker\DockerDesktopWSL`. |

---

## 2. Current configuration

- **Ollama models:** Windows user variable `OLLAMA_MODELS=E:\FYP\LLMs`; `ollama list` shows `qwen3.5:latest`.
- **Ollama binding:** loopback only, `OLLAMA_HOST=127.0.0.1:11434` (set in `scripts/windows/start_ollama.ps1`). It is never exposed on other interfaces.
- **WSL to Windows access:** `networkingMode=mirrored` in `%UserProfile%\.wslconfig`, so WSL reaches Ollama at `localhost:11434`. The `.wslconfig` backup status is not verified.
- **Caches:** runtime caches on ext4 (`~/cache/huggingface`, `~/cache/pip`, `~/cache/torch`); the master copy on `E:\FYP\cache`. Measured DrvFS load times are 3.5x to 7.4x slower (section 4), so runtime caches stay on ext4.
- **FFmpeg:** native Linux package in WSL.
- **Python:** one unified venv `~/envs/insightex`, plus `~/envs/paddleocr-vl` for PaddleOCR.
- **Environment script:** `env/insightex_env.sh` sets `INSIGHTEX_HOME`, `INSIGHTEX_DATA`, `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE=1`, `OLLAMA_BASE_URL`, `PIP_CACHE_DIR`, `TORCH_HOME`, `LD_LIBRARY_PATH` (idempotency guard `_INSIGHTEX_ENV_LOADED`). `~/.profile` sources it once; `scripts/run_in_env.sh` sources it itself.

---

## 3. Sequential VRAM dynamics and architecture contract

### 3.1 Measured VRAM per stage
Sampled by polling `/usr/lib/wsl/lib/nvidia-smi` and the Windows host `nvidia-smi`.

| Stage | Idle before launch | Peak | Peak % of 8,192 MiB | Net delta | Headroom | After exit | Clean release |
|---|---|---|---|---|---|---|---|
| System idle | 994 to 1,167 MiB | n/a | n/a | n/a | 7,025 to 7,198 MiB | 994 to 1,167 MiB | baseline (Windows desktop and IDE) |
| Whisper medium (fp16, 30 s clip) | 1,007 | 4,026 | 49.15% | +3,019 | 4,166 | 1,007 | yes (process exit) |
| Whisper large-v3 (fp16, 10 min) | 1,006 | 5,530 | 67.51% | +4,524 | 2,662 | 1,006 | yes (process exit) |
| BAAI/bge-m3 (CUDA) | 748 | 3,089 | 37.71% | +2,341 | 5,103 | 748 | yes (CARRIED OVER, 2 Oct) |
| Ollama qwen3.5, `num_ctx` 4096 | 1,002 | 7,426 | 90.65% | +6,424 | 766 | 1,002 | yes (`keep_alive: 0`) |
| Ollama qwen3.5, `num_ctx` 8192 | 1,002 | 7,566 | 92.36% | +6,564 | 626 | 1,002 | yes (`keep_alive: 0`) |

### 3.2 Headroom and desktop sharing
- The 8,192 MiB pool is shared with the Windows desktop (about 994 to 1,167 MiB at idle across sessions).
- Headroom is `8,192 - peak`. At `num_ctx` 8192 the peak was 7,566 MiB, leaving 626 MiB.
- `ollama ps` reports 5.6 GB for the model while the host `nvidia-smi` delta over idle was 6,564 MiB (gap about 964 MiB). Under WDDM, per-process memory is not available without admin rights, so the cause of the gap was not tested.

### 3.3 Architecture contract
1. **Zero concurrent CUDA stages.** Whisper (CTranslate2) and bge-m3 (PyTorch) hold persistent device pools; Ollama at 7,566 MiB leaves 626 MiB, so running any stage next to it risks CUDA out-of-memory.
2. **Subprocess isolation.** FFmpeg, Whisper, Ollama extraction and bge-m3 each run as an independent process that fully exits before the next starts.
3. **Ollama batch lifecycle.** Use `keep_alive: "10m"` during a batch; at the end call unload with `keep_alive: 0` in a `finally` block and poll `ollama ps` until the model is gone (section 6.5).

---

## 4. Model load latency (ext4 vs DrvFS)

Cold = Linux page cache dropped (`sync; echo 3 > /proc/sys/vm/drop_caches`); warm = immediate reload.

| Model | Location | Cold (s) | Warm (s) | Warm vs cold | Peak VRAM |
|---|---|---|---|---|---|
| whisper-medium | ext4 | 3.76 | 0.66 | 5.70x | 3,112 MiB |
| whisper-medium | DrvFS | 16.51 | 4.90 | 3.37x | 3,112 MiB |
| whisper-large-v3 | ext4 | 8.37 | 2.03 | 4.12x | 4,936 MiB |
| whisper-large-v3 | DrvFS | 29.64 | 8.64 | 3.43x | 4,645 MiB |
| bge-m3 | ext4 | 6.25 | 1.70 | 3.68x | 3,089 MiB |
| bge-m3 | DrvFS | 27.50 | 10.26 | 2.68x | 3,089 MiB |

bge-m3 load times were measured on 2 October 2026 and not re-run (CARRIED OVER).

- Cold speedup on ext4: medium 4.39x, large-v3 3.54x, bge-m3 4.40x (range 3.5x to 4.4x).
- Warm speedup on ext4: medium 7.42x, large-v3 4.26x, bge-m3 6.04x (range 4.3x to 7.4x).
- `drop_caches` does not flush the Windows NTFS cache, so the true cold DrvFS penalty may be larger.

---

## 5. Whisper audio verification and speed (30 s clip)

Data: `clip_30s.wav` (16 kHz mono), `language="ur"`, `beam_size=5`, `vad_filter=True`, `word_timestamps=True`, fp16 on CUDA.

### 5.1 Timings (recomputed with `statistics.median`)

| Condition | Cold (run 1) | Warm runs (2 to 5) | Warm median | Warm min / max | Warm mean | Speed factor | RTF |
|---|---|---|---|---|---|---|---|
| Order 1: large-v3 | 4.40 s | 3.37, 3.36, 3.37, 3.33 | 3.365 s | 3.33 / 3.37 | 3.357 s | 8.92x | 0.1122 |
| Order 1: medium | 7.75 s | 10.68, 9.45, 13.46, 11.49 | 11.085 s | 9.45 / 13.46 | 11.270 s | 2.71x | 0.3695 |
| Order 2: medium | 7.67 s | 5.74, 7.66, 4.39, 18.14 | 6.700 s | 4.39 / 18.14 | 8.982 s | 4.48x | 0.2233 |
| Order 2: large-v3 | 3.70 s | 3.39, 2.68, 3.34, 3.33 | 3.335 s | 2.68 / 3.39 | 3.185 s | 9.00x | 0.1112 |
| Extra: medium `temperature=0.0` | 3.46 s | 3.53, 3.55, 3.53, 3.45 | 3.530 s | 3.45 / 3.55 | 3.515 s | 8.50x | 0.1177 |

### 5.2 Per-segment metrics

| Condition | Run | Segments | Mean avg_logprob | Min avg_logprob | Max compression_ratio |
|---|---|---|---|---|---|
| medium (default) | cold | 4 | -0.2323 | -0.2323 | 2.3984 |
| medium (default) | warm | 7 | -0.7229 | -0.7229 | 2.1056 |
| medium (`temperature=0.0`) | cold | 12 | -0.2774 | -0.2784 | 2.4144 |
| medium (`temperature=0.0`) | warm | 12 | -0.2774 | -0.2784 | 2.4144 |
| large-v3 (default) | cold | 18 | -0.1082 | -0.1499 | 2.1582 |
| large-v3 (default) | warm | 18 | -0.1082 | -0.1499 | 2.1582 |

### 5.3 Observations (this clip only)
1. `medium` with default settings triggered the temperature-fallback loop on 4 of 5 runs (temperature up to 0.8 and 1.0), causing multi-pass decoding and run times from 4.39 s to 18.14 s.
2. With `temperature=0.0` the extra passes and the variance disappeared (warm median 3.530 s, 8.50x real time).
3. In the warm run, medium-default produced 7 segments and kept English technical terms in Latin script (`machine learning`, `softwareات`, `server`); medium-temp0 produced 12 segments and transliterated the same terms into Urdu script. 5 of 5 matched-start segments differed in text.
4. `large-v3` completed all runs at temperature 0.0 with no fallback, warm median 3.335 to 3.365 s (8.92x to 9.00x real time).
5. These numbers describe `clip_30s.wav` only. No general claim of equality or superiority is made; the checkpoint choice needs a WER evaluation (still open).

---

## 6. Ollama batch contract

### 6.1 Model identity
- Name `qwen3.5:latest`, short ID `6488c96fa5fa`.
- Manifest digest `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7` (709 bytes).
- Weights blob `sha256:dec52a44569a2a25341c4e4d3fee25846eed4f6f0b936278e3a3c900bb99d37c` (6,594,462,816 bytes).
- The ID is constant across all raw logs on disk; no script calls pull, create, cp or delete.

### 6.2 Findings
- **keep_alive:** cold loads after each unload showed an 8.7 s `load_duration`; with `keep_alive: "10m"` the per-chunk load duration was 0.00 s. Unload with `keep_alive: 0` in a `finally` block returned VRAM to baseline within 2.5 s. No run used `keep_alive: 0` on every call.
- **Schema vs `format="json"`:** not distinguishable (10/10 valid for both on this data). The JSON Schema additionally enforces the fields and `additionalProperties: false` at the engine level.
- **GPU offload at `num_ctx` 8192:** `ollama ps` showed 100% GPU (5.6 GB, context 8192). No server-log evidence exists for the layer count.

### 6.3 Reproducibility (3 chunks, 3 runs each; JSON Schema, `num_ctx` 8192, `temperature` 0.1)
- **Chunk 02 [61.34 s to 121.38 s]:** set equality True; concepts `Production Environment`, `Development Environment`, `Batch Learning (Offline Learning)`, `Online Learning`; mean Jaccard 1.0000.
- **Chunk 05 [243.32 s to 304.06 s]:** set equality False. Run 1: `Static Machine Learning Model`, `Online Learning (Implied)`, `Recommendation Engine`. Run 2: `Static Machine Learning Model`, `Evolving Business Scenario`, `Recommendation Engine`, `Server-Side Deployment`. Run 3: `Static Machine Learning Model`, `Evolving Business Scenario`, `Recommendation Engine`, `Online Learning`. Jaccards 0.4000, 0.6000, 0.4000; mean 0.4667.
- **Chunk 08 [426.16 s to 487.50 s]:** set equality False. Runs 1 and 2: `Batch Learning`, `Online Learning`, `Data Scaling Challenges`; run 3 adds `Periodic Retraining`. Jaccards 1.0000, 0.7500, 0.7500; mean 0.8333.

### 6.4 Status
JSON schema validity was 100% on 10 real transcript chunks. Concept extraction quality for knowledge-graph construction has **not** been evaluated and stays **provisional** until a human reviews the transcript and extracted concepts. The call contract is not final.

### 6.5 Recommended pipeline request body and unload contract

#### Batch inference request
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
`num_predict` note: the maximum observed `eval_count` across all chunk runs was 400 tokens, so 600 gives a 50% margin while capping runaway generation.

#### Batch unload contract (execute in a `finally` block)
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

## 7. Execution architecture

### 7.1 Launcher rule (`scripts/run_in_env.sh`)
All stages are launched through the wrapper:
```bash
bash ~/insightex/scripts/run_in_env.sh <command>
```
Failure mode without the wrapper (non-login, non-interactive `wsl -d Ubuntu-24.04 bash ...`):
1. `import ctranslate2` succeeds, and `ctranslate2.get_cuda_device_count()` succeeds (prints 1).
2. `WhisperModel("medium", device="cuda").transcribe(...)` fails with `RuntimeError: Library libcublas.so.12 is not found or cannot be loaded`. The error appears at model tensor execution (`model.encode(features)`), not at import.
3. System `python3` lacks the project dependencies (`ModuleNotFoundError: No module named 'ctranslate2'`).

Through the wrapper, `LD_LIBRARY_PATH` includes the 16 CUDA library directories of the `nvidia-*` venv packages and GPU transcription succeeds.

### 7.2 Offline protocol (`HF_HUB_OFFLINE=1`)
`HF_HUB_OFFLINE=1` is global. To add a HuggingFace model (needs approval, it downloads):
1. `HF_HUB_OFFLINE=0 HF_HOME=$INSIGHTEX_MODEL_CACHE_MASTER/huggingface python3 -c "from huggingface_hub import snapshot_download; snapshot_download('<REPO_ID>')"`
2. `cp -ru $INSIGHTEX_MODEL_CACHE_MASTER/huggingface/hub/models--<MODEL_NAME> ~/cache/huggingface/hub/`
3. Run `tools/audit_env/run_F7_check.py` to confirm zero SHA256 mismatches between master and ext4.

---

## 8. Shell and system verification (3 October 2026)

- **Result: PARTIAL.** `fsutil dirty query E:` needed administrator rights and was not run.
- **`~/.bashrc` history:** earlier edits added DrvFS cache exports that were later cleaned up; the full pre-edit `.bashrc` is not recoverable, so lost lines are unverified beyond those exports.
- **`%UserProfile%\.wslconfig`:** CreationTime and LastWriteTime both 3 Oct 2026 12:33:02. Overwriting can preserve CreationTime, so a prior `.wslconfig` is not ruled out (unverified).
- **Filesystem:** `dmesg` filtered for error/ext4/corrupt/I/O/recover/orphan showed no ext4 or I/O errors; `journalctl -b -p warning` returned 3 lines (init mount, `systemd-sysctl` netfilter), no storage errors; Windows `Get-Volume -DriveLetter E` reported Healthy / OK.
- **Migration (4 October 2026):** startup now sources `env/insightex_env.sh` once from `~/.profile`; see `docs/reports/MIGRATION_REPORT.md` for check results.

---

## 9. Unverified or carried-over items

- bge-m3 load time and VRAM (2 Oct, not re-run); FAISS, NetworkX, PaddleOCR, Docker rows (not re-verified on 3 Oct).
- Concept-extraction quality (needs human review).
- `.wslconfig` prior existence and backup status; E: dirty bit.
- PaddleX cache size difference: `~/.paddlex` about 1,985 MB vs `E:\FYP\cache\paddlex` about 302 MB.

---

## 10. Verdict (as of 3 October 2026)

1. **Ready for Module 1 transcription work (FFmpeg then Whisper): YES.** The 10-minute extraction took 3.24 s; `faster-whisper large-v3` transcribed all 307 segments in 66.69 s (9.00x real time, peak 5,530 MiB); VRAM returned to the 1,006 MiB baseline; no hash mismatches between master and ext4.
2. **Ready for Module 1 concept extraction (Ollama contract): YES, provisional on transcript review.** `qwen3.5:latest` (`6488c96fa5fa`) on loopback, 100% GPU offload at `num_ctx` 8192 (peak 7,566 MiB, 626 MiB headroom), 100% schema validity on 10 real chunks; `keep_alive: "10m"` removed the 8.8 s per-chunk reload; memory unloads cleanly at batch end.
