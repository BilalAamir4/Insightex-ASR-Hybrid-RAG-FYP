# Structure Audit: Insightex (FYP) Repository

**Audit Date:** 4 October 2026  
**Auditor:** Antigravity Pair-Programming Agent  
**Repository Root:** `E:\FYP` (accessed in WSL2 as `/mnt/e/FYP`)  
**Target Audience:** Engineering team and incoming AI agents (Claude Code) preparing for codebase restructuring.  
**Constraint Adherence:** No existing files were moved, renamed, edited, or deleted. All findings are strictly descriptive of the current state; no refactoring or restructuring is performed in this document.

---

## 1. Overview

### 1.1 Current Repo State Summary
The repository currently represents the **pre-pipeline evaluation and environment-validation stage** of "Insightex" (an undergraduate final-year project for timestamp-grounded lecture video indexing and retrieval across code-switched Urdu/English speech). Despite architectural plans for an end-to-end multi-stage pipeline, API serving, and web interfaces, **no unified pipeline application, backend server, or frontend UI currently exists in code**. Instead, the repository consists of standalone evaluation scripts, hardware/environment probes, empirical benchmark drivers, decision reports, cached deep learning models, raw evaluation datasets for a single test lecture, and disk images for WSL2 and Docker. Furthermore, the repository is **not a git repository** (no `.git` directory exists anywhere in the tree), and no global `.gitignore` is present.

### 1.2 Languages, Frameworks, and Declared Dependencies
- **Primary Languages:** Python 3.12 (WSL2 Ubuntu 24.04 and local venv), Bash shell scripting, PowerShell (Windows host wrappers).
- **Core ML Frameworks & Runtimes:**
  - `torch==2.11.0+cu128` (PyTorch with CUDA 12.8 support).
  - `ctranslate2==4.8.2` and `faster-whisper==1.2.1` (C++ inference engine for Whisper ASR).
  - `sentence-transformers==6.1.0` and `transformers==5.18.0` (Dense text embedding).
  - `faiss-cpu==1.15.1` (Dense vector indexing and inner-product similarity search).
  - `networkx==3.6.1` (Graph data structures).
  - `paddlepaddle-gpu==3.2.1` and `paddleocr==3.7.0` (PaddleOCR-VL document/formula parser in dedicated venv `~/envs/paddleocr-vl`).
  - `ollama` (External Windows service running Ollama 0.33.3 serving `qwen3.5:latest` 9.7B Q4_K_M).
  - `ffmpeg` (Native Linux package `6.1.1-3ubuntu5` inside WSL2; Windows binary `8.1.2-essentials` on host).
- **Dependency Declarations:**
  - `requirements.lock.txt` (Root, 84 lines): Pinned lockfile for the primary WSL environment (`~/envs/insightex`).
  - `embedding/requirements.lock.txt` (Subdirectory, 68 lines): Older, superseded lockfile specific to the embedding bake-off subproject.

### 1.3 How the Project is Currently Run (Entry Points & Execution Modes)
The project does not possess a single entry point (e.g. `main.py`, `app.py`, or `docker-compose.up`). Work is executed stage-by-stage as standalone scripts.
- **Environment Execution Wrapper (WSL2):**  
  Empirically verified in `tools/env_audit/ENV_AUDIT_REPORT.md` and `CLAUDE.md`: All WSL-based GPU execution must pass through the wrapper:
  ```bash
  bash /mnt/e/FYP/tools/env_audit/run_in_env.sh python <script_path>.py [args]
  ```
  *(Verified: `run_in_env.sh` sources `env/insightex_env.sh` to configure CUDA `LD_LIBRARY_PATH`, `HF_HOME`, `HF_HUB_OFFLINE=1`, and activates `~/envs/insightex`).*
- **Embedding Bake-Off Entry Point:**
  ```bash
  # Inside WSL2 under /mnt/e/FYP/embedding
  python tools/eval_embeddings/embed_bakeoff.py \
    --srt data/day04_batch_vs_online/whisper_urdu.srt \
    --queries tools/eval_embeddings/queries.csv \
    --out tools/eval_embeddings/results_seq1024 \
    --max-seq-length 1024
  ```
  *(Verified from script arguments in `embedding/tools/eval_embeddings/embed_bakeoff.py` and records in `CLAUDE.md`).*
- **Embedding Unit Tests:**
  ```bash
  python -m pytest tools/eval_embeddings/test_bakeoff.py
  ```
  *(Verified from test definitions in `embedding/tools/eval_embeddings/test_bakeoff.py`).*
- **PaddleOCR-VL Visual Probe:**
  ```powershell
  # Executed from Windows PowerShell
  .\tools\vl_probe\run_probe.ps1 -RunLabel "1"
  ```
  *(Verified from script definition in `tools/vl_probe/run_probe.ps1`).*
- **Whisper 10-Minute Extraction & Benchmark:**
  ```bash
  bash /mnt/e/FYP/tools/env_audit/run_in_env.sh python /mnt/e/FYP/tools/env_audit/process_a_whisper.py
  ```
  *(Verified from script definition in `tools/env_audit/process_a_whisper.py`).*
- **Ollama LLM Verification:**
  ```powershell
  # Windows host: Launch Ollama service
  .\tools\env_audit\start_ollama.ps1
  ```
  ```bash
  # WSL2: Run contract test
  bash /mnt/e/FYP/tools/env_audit/run_in_env.sh python /mnt/e/FYP/tools/env_audit/ollama_contract.py
  ```
  *(Verified from script definition in `tools/env_audit/ollama_contract.py`).*

---

## 2. Full Annotated Directory Tree

Excluded runtime caches and virtual environments:
- `.git`: Non-existent (not a git repository).
- `node_modules`: Non-existent.
- `embedding/.venv/`: ~7,220 MB (39,253 files) — Python 3.12 virtual environment (superseded by WSL internal `~/envs/insightex`).
- `embedding/.pytest_cache/`: ~0.08 MB (6 files) — Pytest test runner cache.
- `tools/vl_probe/__pycache__/`: ~0.01 MB (1 file: `probe.cpython-312.pyc`).
- `embedding/tools/eval_embeddings/__pycache__/`: ~0.07 MB (2 files: `.pyc` artifacts).
- `wsl/Ubuntu-24.04/ext4.vhdx`: 36,892 MB (~36.03 GB) — WSL2 ext4 virtual disk image.
- `docker/DockerDesktopWSL/disk/docker_data.vhdx`: 4,191 MB (~4.09 GB) — Docker Desktop virtual disk image.
- `docker/DockerDesktopWSL/main/ext4.vhdx`: 100 MB — Docker Desktop WSL distro image.
- `cache/huggingface/`: 10,845 MB (~10.59 GB) — Master HuggingFace model cache (`bge-m3`, `qwen3-embedding`, `whisper-medium`, `whisper-large-v3`).
- `cache/pip/`: 1,162 MB (~1.13 GB) — Pip package cache wheels.
- `cache/paddlex/`: 301 MB — PaddleOCR model weights.
- `LLMs/blobs/`: 6,289 MB (~6.14 GB) — Ollama model layer blobs (including 6.59 GB weights for `qwen3.5:latest`).

Annotated tree of active project components:

```text
E:\FYP\
├── CLAUDE.md                             # High-level architecture, environment rules, and VRAM contract for Claude Code
├── requirements.lock.txt                 # Pinned Python package dependencies for the primary WSL environment (~/envs/insightex)
│
├── cache\                                # Master binary cache store on NTFS (prevents re-downloading across WSL distros)
│   ├── huggingface\                      # Master HuggingFace hub cache (models--BAAI--bge-m3, models--Systran--faster-whisper-*, etc.)
│   ├── paddle\                           # Empty directory reserved for Paddle framework cache
│   ├── paddlex\                          # Official models for PaddleX layout detection and PP-OCR
│   ├── pip\                              # Pip wheel cache
│   └── torch\                            # PyTorch model cache directory
│
├── data\                                 # Raw lecture video and benchmark evaluation assets
│   ├── day04_batch_vs_online\            # Benchmark test lecture: "100 Days of ML, Day 4"
│   │   ├── raw\                          # Raw lecture input media
│   │   │   └── lecture_test.mp4          # 11:28 minute test video (50.6 MB, 1080p, code-switched Urdu/English)
│   │   └── eval\                         # Audio extractions, reference transcripts, and generated whisper outputs
│   │       ├── clip_30s.wav              # 30.0s 16kHz mono WAV snippet used for Whisper timing/temperature benchmarks (0.96 MB)
│   │       ├── lecture_first10min.wav    # First 10 minutes 16kHz mono WAV extracted from lecture_test.mp4 (19.2 MB)
│   │       ├── manual_roman.txt          # Human reference transcription of the lecture in Roman Urdu (12.9 KB)
│   │       ├── whisper_large_v3_first10min.json # 307 transcribed segments with timestamps & logprobs from large-v3 (54.3 KB)
│   │       └── whisper_urdu.srt          # Whisper-transcribed Urdu-script subtitle file (40.8 KB, 640 cues)
│   └── frames\                           # Test frames for the visual pipeline
│       ├── eq1.png                       # Test image containing a clean quadratic formula (136.7 KB)
│       └── out\                          # Artifacts generated by the PaddleOCR-VL probe
│           ├── eq1.md                    # LaTeX formula output exported by PaddleOCR-VL ($$\frac{-b\pm\sqrt{...}}{2a}$$)
│           ├── eq1_layout_det_res.png    # Layout detection visual bounding box overlay
│           ├── eq1_res.json              # Full structured JSON output with bounding boxes, polygons, and block types
│           ├── key_inventory.txt         # Dump of dictionary keys and types returned by PaddleOCRVL
│           ├── REPORT.md                 # Summary report of the visual probe run
│           └── vram_run*.csv             # nvidia-smi 500ms memory polling traces for probe runs 1, 2, a, b, c
│
├── docker\                               # Docker storage directory relocated to E: drive
│   └── DockerDesktopWSL\
│       ├── disk\docker_data.vhdx         # Docker container data disk (4.19 GB)
│       └── main\ext4.vhdx                # Docker Desktop WSL distribution disk (100 MB)
│
├── docs\                                 # Formal technical evaluation reports and decision records
│   ├── Embedding Report.md               # Extensive report documenting the BGE-M3 vs Qwen3 bake-off and 30s window decision
│   └── OCR_report.md                     # Feasibility report evaluating PaddleOCR-VL speed, VRAM, and stability
│
├── embedding\                            # Subproject workspace dedicated to the embedding model bake-off
│   ├── requirements.lock.txt             # Pinned lockfile for the embedding bake-off virtual environment
│   ├── data\
│   │   └── day04_batch_vs_online\
│   │       └── whisper_urdu.srt          # Duplicate copy of data/day04_batch_vs_online/eval/whisper_urdu.srt
│   └── tools\
│       └── eval_embeddings\              # Evaluation scripts, fixtures, and benchmark results
│           ├── embed_bakeoff.py          # Primary evaluation script (SRT windowing, FAISS IndexFlatIP retrieval, Recall/MRR metrics)
│           ├── test_bakeoff.py           # Pytest unit tests verifying timestamp parsing, window clipping, overlap logic
│           ├── queries.csv               # 28 human-annotated test queries (15 English, 8 hard paraphrases, 5 Roman Urdu)
│           ├── selftest\                 # Deterministic synthetic fixture used for offline dry-runs and regression tests
│           │   ├── fake_queries.csv      # 5 synthetic test queries matching fake_transcript.srt
│           │   ├── fake_transcript.srt   # 20 synthetic cues across 180 seconds
│           │   ├── output_dryrun\        # Benchmark output artifacts using fake hash embedder (--dry-run)
│           │   ├── output_offline\       # Benchmark output artifacts using real weights under offline mode
│           │   └── output_real\          # Benchmark output artifacts from initial fixture test
│           ├── results\                  # First bake-off run with 512 max-seq-length (OUTDATED due to Qwen3 truncation)
│           │   ├── analysis.md           # Outdated analysis narrative
│           │   ├── doc_updates.md        # Staged draft edits for proposal/feature documentation
│           │   ├── per_query_results.csv # Query-by-query ranks, scores, and hit flags
│           │   ├── run_config.json       # Run configuration metadata, hashes, package versions
│           │   ├── summary.csv           # Aggregated Recall@1/3/5 and MRR per window size
│           │   ├── summary.md            # Markdown summary table
│           │   ├── window_comparison.md  # Detailed comparison across 30s, 60s, and 90s windows
│           │   └── windows_W*.csv        # Generated text chunks for 30s, 60s, and 90s windows
│           └── results_seq1024\          # FINAL AUTHORITATIVE bake-off run with 1024 max-seq-length
│               ├── per_query_results.csv # Per-query evaluation records for BGE-M3 and Qwen3
│               ├── run_config.json       # Execution metadata, model prefixes, git/file hashes
│               ├── summary.csv           # Definitive benchmark metrics (Recall@1/3/5, MRR, VRAM, latency)
│               ├── summary.md            # Formatted table of final results
│               └── windows_W*.csv        # Exact window splits (W30: 23 windows, W60: 12 windows, W90: 8 windows)
│
├── env\                                  # Shell environment configuration
│   └── insightex_env.sh                  # Bash environment script setting HF_HOME, offline flags, and dynamic CUDA LD_LIBRARY_PATH
│
├── LLMs\                                 # Storage directory for Ollama model layers and manifests
│   ├── blobs\                            # Content-addressable sha256 layer blobs (includes 6.59 GB Qwen 3.5 weights)
│   └── manifests\registry.ollama.ai\library\qwen3.5\
│       └── latest                        # Ollama model manifest linking blobs for qwen3.5:latest
│
├── tools\                                # System tools, hardware benchmarks, environment verification scripts
│   ├── env_audit\                        # Comprehensive test suite and audit scripts for WSL, CUDA, Whisper, and Ollama
│   │   ├── ENV_AUDIT_REPORT.md           # Authoritative audit document recording system state, VRAM limits, and contract
│   │   ├── run_in_env.sh                 # Standard execution wrapper sourcing insightex_env.sh and activating venv
│   │   ├── start_ollama.ps1              # Windows host PowerShell script to run Ollama bound to 127.0.0.1:11434 with models on E:
│   │   ├── process_a_whisper.py          # Benchmark pipeline runner: FFmpeg audio extraction + faster-whisper large-v3
│   │   ├── ollama_contract.py            # Comprehensive Ollama test runner (JSON Schema vs json, context sizes, batch unload)
│   │   ├── whisper_anomaly_audit.py      # Detailed benchmark investigating Whisper medium vs large-v3 temperature fallback
│   │   ├── check_*.py / check_*.sh       # System state checks (av, env_vars, file integrity, imports, login env, packages, paths)
│   │   ├── smoke_*.py                    # Minimal execution smoke tests for embedding, faiss/networkx, ollama, paddleocr
│   │   ├── test_*.py                     # Quick API and engine verification tests for Ollama and Whisper
│   │   ├── verify_6*.py                  # Verification scripts for Whisper, BGE-M3, loadtimes, Ollama, FAISS, sequential VRAM
│   │   ├── run_T*.py / run_T*.sh         # Test runners for audit tasks T0–T5 (ports, cache integrity, contracts, anomaly, shell)
│   │   ├── run_F*.py / run_F*.sh         # Followup audit runners F1–F7 (model identity, reproducibility, segments, unload, wrapper)
│   │   ├── load_single_model.py          # Isolated model loader for measuring cold/warm latency
│   │   ├── run_loadtimes_benchmark.py    # Cross-filesystem benchmark runner comparing ext4 vs DrvFS
│   │   ├── loadtimes_results.json        # Raw benchmark timings comparing ext4 and DrvFS load times
│   │   ├── compare_caches.py             # File size and hash comparison between master cache on E: and runtime cache on ext4
│   │   ├── probe_ollama.py / probe_think.py # Specific probes for Ollama streaming and thinking behavior
│   │   ├── fail_mode_test.sh / fail_whisper_test.py # Deliberate failure harness testing execution without run_in_env.sh
│   │   ├── update_shell_env.py / print_bashrc.sh    # Utilities to inspect and clean ~/.bashrc
│   │   └── results\                      # Captured standard outputs and metrics from audit runs
│   │       ├── followup\                 # Outputs from tasks T0, T1, T2, T2_process_a, T3, T4, T5
│   │       └── followup2\                # Outputs from tasks F1, F2, F3, F3_segments.json, F4, F5, F6, F7
│   └── vl_probe\                         # Visual pipeline evaluation probe for PaddleOCR-VL
│       ├── probe.py                      # Python script evaluating PaddleOCRVL construction, latency, VRAM, and JSON/LaTeX export
│       └── run_probe.ps1                 # PowerShell harness polling VRAM baseline, launching probe with timeout, sampling memory
│
└── wsl\                                  # WSL2 storage directory relocated to E: drive
    └── Ubuntu-24.04\
        └── ext4.vhdx                     # WSL2 virtual hard disk containing Ubuntu 24.04 OS, user homes, and ext4 caches (36.89 GB)
```

---

## 3. Directory-by-Directory Breakdown

### 3.1 `E:\FYP\` (Root)
- **What it contains:** `CLAUDE.md`, `requirements.lock.txt`, and high-level project directories.
- **Why it exists:** Serves as the master repository root and Windows workspace. All project storage is strictly confined under `E:\FYP` to avoid filling host drive `C:`.
- **Status:** **Working**.
  - *Evidence:* Host workspace is active; dependencies and guidelines are established.
- **Depends on / used by:** Primary entry point for developer and agent operations.
- **Notable issues:**
  - Not initialized as a git repository (`git status` fails; no `.git` folder).
  - No root `.gitignore` file exists.
  - No unified project documentation (`README.md`) exists.

---

### 3.2 `E:\FYP\env\`
- **What it contains:**
  - `insightex_env.sh`: Shell configuration script for WSL2.
- **Why it exists:** Establishes global environment variables required for offline execution, cache redirection, Ollama endpoint targeting, and CUDA library discovery for CTranslate2.
- **Status:** **Working**.
  - *Evidence:* Verified in `tools/env_audit/verify_env_fix.sh`; loaded successfully in `run_in_env.sh`.
- **Depends on / used by:** Sourced by `tools/env_audit/run_in_env.sh` and user shells.
- **Notable issues:**
  - Hardcodes user-specific paths:
    ```bash
    export HF_HOME="/home/bilal_aamir/cache/huggingface"
    export PIP_CACHE_DIR="/home/bilal_aamir/cache/pip"
    export TORCH_HOME="/home/bilal_aamir/cache/torch"
    NVIDIA_SITE="/home/bilal_aamir/envs/insightex/lib/python3.12/site-packages/nvidia"
    ```
    This script will break if executed under a different WSL username or distro path.

---

### 3.3 `E:\FYP\docs\`
- **What it contains:**
  - `Embedding Report.md`: Comprehensive engineering record of the embedding bake-off (BGE-M3 vs Qwen3-Embedding-0.6B), window evaluation, and decision rationale.
  - `OCR_report.md`: Feasibility evaluation of PaddleOCR-VL 0.9B on lecture slides, detailing memory allocation, latency, and stability risks.
- **Why it exists:** Serves as the authoritative architectural decision record for Milestone 4 (Embeddings) and Milestone 2 (Visual/OCR).
- **Status:** **Working**.
  - *Evidence:* Both documents contain fully verified empirical tables, methodology logs, and explicit decisions signed off on 1–3 October 2026.
- **Depends on / used by:** Guides all future retrieval and visual pipeline implementations.
- **Notable issues:**
  - File naming inconsistency: `Embedding Report.md` uses spaces; `OCR_report.md` uses snake_case with underscores.

---

### 3.4 `E:\FYP\data\`
- **What it contains:**
  - `data/day04_batch_vs_online/raw/lecture_test.mp4`: 11:28 test lecture video.
  - `data/day04_batch_vs_online/eval/`: Extracted WAV clips (`clip_30s.wav`, `lecture_first10min.wav`), manual Roman-Urdu ground truth (`manual_roman.txt`), Whisper Urdu SRT (`whisper_urdu.srt`), and generated JSON segment data (`whisper_large_v3_first10min.json`).
  - `data/frames/eq1.png` and `data/frames/out/`: Quadratic formula test slide and PaddleOCR-VL output exports (Markdown, JSON, bounding boxes, memory CSVs).
- **Why it exists:** Serves as the empirical dataset for all benchmark experiments.
- **Status:** **Working**.
  - *Evidence:* Audio files are valid 16kHz mono WAVs; SRT contains 640 timestamped cues; JSON files parse with standard schemas.
- **Depends on / used by:** Consumed by `process_a_whisper.py`, `embed_bakeoff.py`, `ollama_contract.py`, and `probe.py`.
- **Notable issues:**
  - `whisper_urdu.srt` is duplicated verbatim in `embedding/data/day04_batch_vs_online/whisper_urdu.srt` (identical SHA256: `c0355747...`).
  - Generated evaluation artifacts (`data/frames/out/`, `data/day04_batch_vs_online/eval/`) sit alongside raw source inputs rather than in a segregated output directory.

---

### 3.5 `E:\FYP\tools\env_audit\`
- **What it contains:**
  - Central reports: `ENV_AUDIT_REPORT.md` (authoritative environment audit).
  - Wrapper scripts: `run_in_env.sh`, `start_ollama.ps1`.
  - Core pipeline evaluation scripts: `process_a_whisper.py`, `ollama_contract.py`, `whisper_anomaly_audit.py`.
  - Verification & benchmark scripts: `verify_6*.py`, `load_single_model.py`, `run_loadtimes_benchmark.py`, `compare_caches.py`.
  - Formal audit suites: `run_T0.py` through `run_T5.py`, `run_F1_audit.py` through `run_F7_check.py`.
  - Smoke tests and failure checks: `smoke_*.py`, `test_*.py`, `fail_mode_test.sh`.
  - Captured run logs: `results/followup/` (T0–T5) and `results/followup2/` (F1–F7).
- **Why it exists:** Created to audit, validate, and debug the heterogeneous development environment (Windows host Ollama + WSL2 CUDA + ext4 vs DrvFS file systems) and prove hardware limits on the RTX 3070 8GB GPU.
- **Status:** **Working / Completed**.
  - *Evidence:* Fully executed on 3 October 2026; generated comprehensive results in `results/` and verified in `ENV_AUDIT_REPORT.md`.
- **Depends on / used by:** Depends on `env/insightex_env.sh`, WSL venv `~/envs/insightex`, Ollama on host `127.0.0.1:11434`, and cache models.
- **Notable issues:**
  - High degree of script duplication and sprawl (55 files in a single flat directory).
  - Multiple test scripts perform near-identical checks (e.g., `test_whisper.py`, `test_whisper_direct.py`, `verify_6a_whisper.py`, `whisper_anomaly_audit.py`).
  - Hardcoded paths to `/home/bilal_aamir/` and `/mnt/e/FYP/` throughout the python scripts.

---

### 3.6 `E:\FYP\tools\vl_probe\`
- **What it contains:**
  - `probe.py`: Python script loading `PaddleOCRVL()`, timing warm-up and steady-state inference, measuring Paddle memory allocators, and saving JSON/Markdown.
  - `run_probe.ps1`: Windows PowerShell harness enforcing pre-run VRAM idle checks (<800 MiB), invoking WSL probe under a 600s timeout, and logging `nvidia-smi` samples.
- **Why it exists:** Evaluates the feasibility of PaddleOCR-VL for Feature 13 (Visual Pipeline).
- **Status:** **Experimental**.
  - *Evidence:* Completed feasibility probe, but documented 2 hangs out of 5 runs due to GPU allocator reserving 7.1 GB VRAM (`OCR_report.md`).
- **Depends on / used by:** Depends on isolated WSL venv `~/envs/paddleocr-vl` (does not run inside `~/envs/insightex`).
- **Notable issues:**
  - Hardcoded Linux path `/mnt/e/FYP/data/frames/eq1.png` in `probe.py`.
  - Hardcoded Windows path `E:\FYP\data\frames\out\` in `run_probe.ps1`.
  - Contains orphaned `__pycache__` directory.

---

### 3.7 `E:\FYP\embedding\`
- **What it contains:**
  - `requirements.lock.txt`: Outdated venv lockfile.
  - `data/day04_batch_vs_online/whisper_urdu.srt`: Duplicate copy of transcript.
  - `tools/eval_embeddings/embed_bakeoff.py`: 706-line CLI evaluation script.
  - `tools/eval_embeddings/test_bakeoff.py`: Unit test suite (7 tests).
  - `tools/eval_embeddings/queries.csv`: 28 evaluation queries.
  - `tools/eval_embeddings/selftest/`: Synthetic test fixture.
  - `tools/eval_embeddings/results/`: Outdated 512-token sequence limit run.
  - `tools/eval_embeddings/results_seq1024/`: Authoritative 1024-token run.
- **Why it exists:** Subproject workspace where the embedding model selection (BGE-M3 vs Qwen3) and chunk window size (30s vs 60s vs 90s) were evaluated and decided.
- **Status:** **Working / Completed**.
  - *Evidence:* Unit tests pass cleanly (`pytest test_bakeoff.py`); results reproducibly saved in `results_seq1024/` and documented in `docs/Embedding Report.md`.
- **Depends on / used by:** Depends on `torch`, `sentence-transformers`, `faiss-cpu`, and cached model `BAAI/bge-m3`.
- **Notable issues:**
  - Nested directory structure (`embedding/tools/eval_embeddings/...`) mimics an internal mini-repo with its own `data/`, `tools/`, and `.venv/`.
  - `embedding/.venv` is 7.2 GB and sits directly on the Windows filesystem (DrvFS), which `ENV_AUDIT_REPORT.md` noted as suffering from severe I/O degradation. `CLAUDE.md` explicitly notes that `embedding/.venv` is superseded by WSL internal `~/envs/insightex`.
  - `results/` is obsolete but retained alongside the valid `results_seq1024/`.

---

### 3.8 `E:\FYP\cache\`
- **What it contains:** Master store for offline models and wheels:
  - `huggingface/hub/models--BAAI--bge-m3` (~4.25 GB)
  - `huggingface/hub/models--Qwen--Qwen3-Embedding-0.6B` (~1.2 GB)
  - `huggingface/hub/models--Systran--faster-whisper-medium` (~1.43 GB)
  - `huggingface/hub/models--Systran--faster-whisper-large-v3` (~2.88 GB)
  - `paddlex/` (~301 MB)
  - `pip/` (~1.16 GB)
- **Why it exists:** Preserves heavy binary assets on the high-capacity NTFS drive `E:` so they are not wiped when rebuilding WSL distros, while ext4 runtime copies (`~/cache/huggingface`) provide high-speed I/O.
- **Status:** **Working**.
  - *Evidence:* Bit-for-bit SHA256 cache integrity verified with 0 mismatches across all blobs (`run_F7_check.py`).
- **Depends on / used by:** Sourced by WSL via `cp -ru` into `~/cache/huggingface/` and referenced by offline tests.
- **Notable issues:**
  - Empty directories `cache/paddle` and `cache/torch`.

---

### 3.9 `E:\FYP\LLMs\`
- **What it contains:**
  - `blobs/`: 4 content-addressable layer blobs, including `sha256-dec52a44569a...` (6,594,462,816 bytes).
  - `manifests/registry.ollama.ai/library/qwen3.5/latest`: Manifest linking the model layers for `qwen3.5:latest` (ID: `6488c96fa5fa`).
- **Why it exists:** Dedicated directory configured via Windows environment variable `OLLAMA_MODELS=E:\FYP\LLMs` to prevent Ollama from downloading multi-gigabyte LLM weights to `C:\Users\<user>\.ollama\models`.
- **Status:** **Working**.
  - *Evidence:* Verified active in `tools/env_audit/start_ollama.ps1` and checked via `ollama list`.
- **Depends on / used by:** Consumed by the Windows Ollama service on `127.0.0.1:11434`.
- **Notable issues:** None. Directory is strictly managed by Ollama engine.

---

### 3.10 `E:\FYP\wsl\` and `E:\FYP\docker\`
- **What they contain:**
  - `wsl/Ubuntu-24.04/ext4.vhdx`: Virtual hard disk for WSL2 Ubuntu 24.04 distro (36.89 GB).
  - `docker/DockerDesktopWSL/disk/docker_data.vhdx` (4.19 GB) and `main/ext4.vhdx` (100 MB).
- **Why they exist:** Relocated virtual hard drives moved from `C:\Users\...\AppData\Local` to `E:\FYP` via `wsl --manage --move` to ensure zero disk growth on `C:`.
- **Status:** **Working**.
  - *Evidence:* WSL2 boots directly from this VHDX; verified healthy in Windows volume queries.
- **Depends on / used by:** Windows Hyper-V and WSL2 subsystem.
- **Notable issues:**
  - These are large proprietary virtual disk binaries sitting inside what will eventually be a git-managed repository. They must be excluded from version control.

---

## 4. Pipeline-to-Code Map

The table below maps each planned stage of the "Insightex" system to the files that implement it in the current codebase:

| Pipeline Stage / Feature | Implementing File(s) | Status | Notes / Evidence |
|---|---|---|---|
| **Audio Extraction (FFmpeg)** | `tools/env_audit/process_a_whisper.py:67-78` | **Implemented (Eval script)** | Extracts 16kHz mono WAV from `lecture_test.mp4` via `/usr/bin/ffmpeg` in 3.24s. No standalone module. |
| **ASR Transcription (Whisper)** | `tools/env_audit/process_a_whisper.py:93-118`, `tools/env_audit/whisper_anomaly_audit.py`, `tools/env_audit/run_F3_segments.py` | **Implemented (Eval scripts)** | `faster-whisper` (`large-v3` and `medium`, CUDA float16) transcribed test clips and generated `whisper_large_v3_first10min.json`. No continuous pipeline runner. |
| **Visual / OCR Pipeline** | `tools/vl_probe/probe.py`, `tools/vl_probe/run_probe.ps1` | **Experimental (Probe only)** | Tested PaddleOCR-VL 0.9B on one frame (`eq1.png`). Feasibility confirmed but prone to GPU allocator hangs (`OCR_report.md`). Gated behind `visual.enabled` flag; not integrated into pipeline. |
| **Segment Fusion / Chunking** | `embedding/tools/eval_embeddings/embed_bakeoff.py:165-212`, `tools/env_audit/ollama_contract.py:127-149` | **Partial** | SRT parsing into fixed 30s/60s/90s windows implemented in bake-off script; Whisper JSON segment grouping into ~60s chunks implemented in Ollama contract script. No unified fusion engine. |
| **LLM Concept Extraction** | `tools/env_audit/ollama_contract.py`, `tools/env_audit/run_F2_repro.py` | **Implemented (Eval script)** | Calls Ollama `qwen3.5:latest` via `/api/chat` with strict JSON Schema (`name`, `description`, `exam_relevant`). Unload contract verified with `keep_alive: 0`. No production service module. |
| **Importance Tagging** | `tools/env_audit/ollama_contract.py:39-44` | **Partial** | Handled solely as a boolean field (`exam_relevant: bool`) within the LLM prompt and JSON schema in evaluation tests. |
| **Knowledge Graph Construction** | `tools/env_audit/smoke_faiss_networkx.py`, `tools/env_audit/verify_6d_faiss_networkx.py` | **Stub / Not Present** | Only basic smoke tests importing NetworkX and creating trivial nodes/edges exist. No graph schema, entity linking, or persistence logic exists. |
| **FAISS Vector Indexing** | `embedding/tools/eval_embeddings/embed_bakeoff.py:499-507`, `tools/env_audit/smoke_faiss_networkx.py` | **Implemented (In-memory eval)** | `IndexFlatIP` on L2-normalized 1024-d BGE-M3 vectors implemented in memory during bake-off. No persistent FAISS index builder or index disk serializer exists. |
| **Query Router (Graph/Vector/Hybrid)** | None | **Not Present** | Architectural concept only; mentioned in `CLAUDE.md` and `Embedding Report.md`. Zero code implementation. |
| **Textbook PDF Chunking** | None | **Not Present** | Blocked awaiting textbook selection (Test B in `docs/Embedding Report.md`). Zero code implementation. |
| **Timestamp-to-Page Fusion** | None | **Not Present** | Dependent on PDF chunking and concept extraction. Zero code implementation. |
| **Video Serving (Nginx range requests)** | None | **Not Present** | Zero nginx configurations, dockerfiles, or media server code present in repo. |
| **API Backend (FastAPI / REST)** | None | **Not Present** | Zero web framework code (FastAPI, Flask, Starlette) present in repo. |
| **Student UI** | None | **Not Present** | Zero frontend code (HTML, CSS, JavaScript, React, Vue, Next.js) present in repo. |
| **Teacher UI** | None | **Not Present** | Zero frontend or administration code present in repo. |
| **Quiz / Notes / Flashcards** | None | **Not Present** | Zero generative study tool implementations. |
| **Highlight Reel Generator** | None | **Not Present** | Zero video cutting or summary assembly implementations. |
| **Voice Interface** | None | **Not Present** | Zero voice capture or TTS implementations. |
| **Sign Language Integration** | None | **Not Present** | Zero gesture recognition or sign translation implementations. |

---

## 5. Data and Artifacts

### 5.1 Storage Locations & Git Status
Because this repository is not yet a git repository, **all files are currently uncommitted on the local filesystem**. When initialized, large media files, model caches, and virtual disk images must be added to `.gitignore`.

| Category | File Path / Directory | Committed / Ignored | Size | Description / Schema |
|---|---|---|---|---|
| **Raw Video** | `data/day04_batch_vs_online/raw/lecture_test.mp4` | Local file (Must ignore) | 50.7 MB | 1080p MP4 test lecture video |
| **Audio Extract** | `data/day04_batch_vs_online/eval/lecture_first10min.wav` | Local file (Must ignore) | 19.2 MB | 16 kHz mono PCM WAV |
| **Audio Benchmark**| `data/day04_batch_vs_online/eval/clip_30s.wav` | Local file (Keep as eval fixture) | 0.96 MB | 30.0s 16 kHz mono WAV |
| **Human Reference**| `data/day04_batch_vs_online/eval/manual_roman.txt` | Local file (Keep) | 12.9 KB | Human reference text in Roman Urdu |
| **ASR Subtitles** | `data/day04_batch_vs_online/eval/whisper_urdu.srt` | Local file (Keep) | 40.8 KB | Standard SubRip (.srt) subtitle cues |
| **ASR Segments** | `data/day04_batch_vs_online/eval/whisper_large_v3_first10min.json` | Local file (Keep) | 54.3 KB | JSON array of segment objects |
| **Visual Frame** | `data/frames/eq1.png` | Local file (Keep as fixture) | 136.7 KB | PNG image of quadratic formula |
| **OCR Result** | `data/frames/out/eq1_res.json` | Local file (Keep) | 2.4 KB | Structured OCR layout JSON |
| **OCR LaTeX** | `data/frames/out/eq1.md` | Local file (Keep) | 42 B | Markdown containing LaTeX display formula |
| **Bake-off Metrics**| `embedding/tools/eval_embeddings/results_seq1024/summary.csv` | Local file (Keep) | 1.7 KB | CSV table of Recall and MRR |
| **Bake-off Windows**| `embedding/tools/eval_embeddings/results_seq1024/windows_W30.csv` | Local file (Keep) | 16.5 KB | Fixed 30s text window chunks |
| **Model Weights** | `cache/huggingface/hub/` | Local file (Must ignore) | 10.8 GB | HuggingFace snapshot blobs |
| **LLM Weights** | `LLMs/blobs/` | Local file (Must ignore) | 6.29 GB | Ollama content-addressable blobs |
| **Disk Images** | `wsl/` and `docker/` | Local file (Must ignore) | 41.0 GB | WSL2 and Docker VHDX virtual disks |

### 5.2 Artifact Schemas and Samples

#### ASR Segment Output (`whisper_large_v3_first10min.json`):
```json
[
  {
    "id": 1,
    "start": 0.0,
    "end": 2.04,
    "text": "Hello guys, welcome to my YouTube channel",
    "avg_logprob": -0.138,
    "no_speech_prob": 0.019
  }
]
```

#### LLM Concept Extraction Schema (Enforced via Ollama `/api/chat` JSON Schema):
```json
{
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
}
```

#### PaddleOCR-VL Parsing Output (`eq1_res.json`):
```json
{
  "input_path": "/mnt/e/FYP/data/frames/eq1.png",
  "width": 486,
  "height": 337,
  "parsing_res_list": [
    {
      "block_label": "display_formula",
      "block_content": " $$ \\frac{-b\\pm\\sqrt{(b^{2}-4ac)}}{2a} $$ ",
      "block_bbox": [47, 94, 420, 275],
      "block_id": 0,
      "block_order": 1,
      "block_polygon_points": [[47.0, 94.0], [420.0, 94.0], [420.0, 275.0], [47.0, 275.0]]
    }
  ]
}
```

#### Embedding Bake-off Window Export (`windows_W30.csv`):
```csv
window_id,start_sec,end_sec,n_cues,text
0,0.000,30.000,16,"Hello guys, welcome to my YouTube channel..."
1,30.000,60.000,15,"Machine learning is no different..."
```

### 5.3 Producer-Consumer Artifact Mapping
```text
lecture_test.mp4
  │
  ├──[process_a_whisper.py (ffmpeg)]──> lecture_first10min.wav
  │                                           │
  │                      [process_a_whisper.py (Whisper large-v3)]
  │                                           │
  │                                           ▼
  │                           whisper_large_v3_first10min.json
  │                                           │
  │                                  [ollama_contract.py]
  │                                           │
  │                                           ▼
  │                                [LLM Concept JSON Output]
  │
  └──[Pre-existing Whisper run]──> whisper_urdu.srt
                                         │
                             [embed_bakeoff.py] <── queries.csv
                                         │
                                         ▼
                             results_seq1024/ (windows_W*.csv, summary.csv)

eq1.png ──>[probe.py (PaddleOCR-VL)]──> data/frames/out/ (eq1.md, eq1_res.json)
```

---

## 6. Configuration and Environment

### 6.1 Configuration Files
- `env/insightex_env.sh`: Sourced by bash wrappers. Defines root paths, offline mode, and dynamic library search paths for CUDA.
- `%UserProfile%\.wslconfig` (Host file): Configured with `networkingMode=mirrored` to allow WSL2 to access Windows Ollama at `localhost:11434`.
- `requirements.lock.txt`: Root lockfile declaring exact package versions.

### 6.2 Environment Variables & Flags
- `HF_HUB_OFFLINE=1`: Set globally in `insightex_env.sh` to prevent unexpected HuggingFace network calls.
- `HF_HOME=/home/bilal_aamir/cache/huggingface`: Points to runtime cache on ext4.
- `PIP_CACHE_DIR=/home/bilal_aamir/cache/pip`: Redirects pip wheel cache.
- `TORCH_HOME=/home/bilal_aamir/cache/torch`: Redirects PyTorch cache.
- `OLLAMA_BASE_URL=http://localhost:11434`: Endpoint for WSL2 HTTP client requests to host Ollama.
- `OLLAMA_MODELS=E:\FYP\LLMs`: Configured in Windows User Environment to store Ollama weights on drive E:.
- `OLLAMA_HOST=127.0.0.1:11434`: Set in `start_ollama.ps1` to prevent binding to public interfaces (`0.0.0.0` was formally rejected for security).
- `visual.enabled`: Mentioned in `CLAUDE.md` and `OCR_report.md` as the architectural toggle flag gating the visual pipeline. *Currently not implemented in any config file or code module.*

### 6.3 Hardcoded Absolute Paths Observed
1. In `env/insightex_env.sh`:
   - `/mnt/e/FYP`
   - `/home/bilal_aamir/cache/huggingface`
   - `/home/bilal_aamir/cache/pip`
   - `/home/bilal_aamir/cache/torch`
   - `/home/bilal_aamir/envs/insightex/...`
2. In `tools/env_audit/run_in_env.sh`:
   - `/mnt/e/FYP/env/insightex_env.sh`
   - `/home/bilal_aamir/envs/insightex/bin/activate`
3. In `tools/env_audit/process_a_whisper.py`:
   - `/mnt/e/FYP/data/day04_batch_vs_online/raw/lecture_test.mp4`
   - `/mnt/e/FYP/data/day04_batch_vs_online/eval/lecture_first10min.wav`
   - `/mnt/e/FYP/data/day04_batch_vs_online/eval/whisper_large_v3_first10min.json`
   - `/usr/lib/wsl/lib/nvidia-smi`
   - `/usr/bin/ffmpeg`
4. In `tools/vl_probe/probe.py`:
   - `/mnt/e/FYP/data/frames/eq1.png`
   - `/mnt/e/FYP/data/frames/out`
5. In `tools/vl_probe/run_probe.ps1`:
   - `E:\FYP\data\frames\out\vram_run$RunLabel.csv`
   - `/mnt/e/FYP/tools/vl_probe/probe.py`
6. In `embedding/tools/eval_embeddings/results_seq1024/run_config.json`:
   - `/mnt/e/FYP/embedding/data/day04_batch_vs_online/whisper_urdu.srt`

### 6.4 GPU / VRAM Handling and Contracts
- **Hardware Budget:** NVIDIA GeForce RTX 3070 with 8,192 MiB VRAM.
- **Desktop Idle Overhead:** 994 MiB to 1,167 MiB consumed by Windows desktop, Antigravity IDE, Claude Desktop, and WebView2.
- **Stage Allocations:**
  - Whisper `large-v3`: Peaks at **5,530 MiB** (67.5% of card).
  - Ollama `qwen3.5:latest` (`num_ctx 8192`): Peaks at **7,566 MiB** (92.4% of card, leaving **626 MiB headroom**).
  - `BAAI/bge-m3`: Peaks at **3,089 MiB** (in standalone evaluation).
  - `PaddleOCR-VL`: Peaks at **~7,950 MiB** reserved allocator pool (working memory ~3,097 MiB).
- **Enforced Execution Contract:**
  1. **Strict Zero-Concurrency:** Two CUDA models must never run concurrently. Whisper, Ollama, and BGE-M3 must run in separate subprocesses.
  2. **Explicit Unload Protocol:** Ollama models must be explicitly unloaded at the end of a batch using `keep_alive: 0` in a `finally` block, followed by polling `ollama ps` until unmapped:
     ```python
     requests.post("http://localhost:11434/api/chat", json={"model": "qwen3.5:latest", "keep_alive": 0})
     ```
  3. **Process Exit Isolation:** Whisper and embedding stages rely on complete Python process termination to return CUDA allocations cleanly to system baseline.

---

## 7. Dependency Graph

### 7.1 Module Import Flow
Because there is no centralized library package (no root `insightex/` package or installed wheels), dependencies are strictly script-level:

```text
[tools/env_audit/run_in_env.sh]
       │ (sources)
       ▼
[env/insightex_env.sh] ──(sets LD_LIBRARY_PATH & HF_HOME)──┐
       │                                                   │
       │ (activates)                                       │
       ▼                                                   │
[~/envs/insightex (WSL venv)]                              │
       │                                                   │
       ├──> faster_whisper ──> ctranslate2 ──(dynamic link)┘
       │         ▲
       │         │ (imports)
       │    [process_a_whisper.py] ──(calls /usr/bin/ffmpeg)
       │    [whisper_anomaly_audit.py]
       │
       ├──> sentence_transformers ──> torch (CUDA cu128)
       │         ▲
       │         │ (imports)
       │    [embed_bakeoff.py] ──> faiss (faiss-cpu)
       │
       └──> requests / urllib ──(HTTP loopback :11434)──> [Ollama Service (Host)]
                 ▲                                                 │ (loads weights from)
                 │ (imports)                                       ▼
            [ollama_contract.py]                             [E:\FYP\LLMs]
            [run_F2_repro.py]
```

### 7.2 Circular or Tangled Dependencies
- There are no Python circular imports because scripts do not import each other; each script is standalone and re-implements utility functions (`get_vram_mb()`, `format_timestamp()`, etc.) locally.
- **Architectural Coupling:** There is tight environmental coupling between the Windows host (which must run Ollama and manage VRAM) and WSL2 (which runs Python and FFmpeg). Scripts like `run_probe.ps1` cross the OS boundary using `wsl -d Ubuntu-24.04 -- bash -lc "..."`.

---

## 8. Problems Observed

### 8.1 Duplicate or Near-Duplicate Files and Logic
- **Transcript SRT Duplication:**
  - `data/day04_batch_vs_online/eval/whisper_urdu.srt`
  - `embedding/data/day04_batch_vs_online/whisper_urdu.srt`  
  *Evidence:* Both files have identical SHA256 hashes (`c035574757d6a220d323911d552b0d5569c0b3e907083b7a1e8acf611a7114ce`).
- **Lockfile Duplication:**
  - `requirements.lock.txt` (Root)
  - `embedding/requirements.lock.txt`  
  *Evidence:* The root lockfile includes full packages (`faster-whisper`, `jsonschema`, etc.), while `embedding/` has an older lockfile retaining superseded packages (`pandas==3.0.6`).
- **Repeated VRAM Sampling Logic:**
  - `tools/env_audit/process_a_whisper.py:32-56`
  - `tools/env_audit/ollama_contract.py:74-95`
  - `tools/env_audit/verify_6b_bge.py:10-30`
  - `tools/env_audit/run_F6_audit.py:27-50`  
  *Evidence:* Identical background `threading.Thread` polling `/usr/lib/wsl/lib/nvidia-smi` is copied verbatim into 4 different scripts.
- **Repeated Whisper Benchmarking Logic:**
  - `tools/env_audit/test_whisper.py`
  - `tools/env_audit/test_whisper_direct.py`
  - `tools/env_audit/verify_6a_whisper.py`
  - `tools/env_audit/whisper_anomaly_audit.py`  
  *Evidence:* All four files perform test loads of `WhisperModel` on CUDA float16 with minor parameter variations.

### 8.2 Dead, Outdated, or Orphaned Files
- **Outdated 512-Token Bake-Off Results:**
  - `embedding/tools/eval_embeddings/results/` (`analysis.md`, `summary.csv`, `summary.md`, `windows_W*.csv`)  
  *Evidence:* `CLAUDE.md` line 65 and `docs/Embedding Report.md` line 121 explicitly note: *"The first run's analysis is therefore outdated; use only the 1024 run (`results_seq1024/`)."*
- **Superseded Virtual Environment:**
  - `embedding/.venv/` (~7.2 GB)  
  *Evidence:* `CLAUDE.md` line 23 explicitly notes: *"embedding/.venv is the older bake-off venv, superseded by ~/envs/insightex."*
- **Empty Directories:**
  - `cache/paddle/` (0 bytes, 0 files)
  - `cache/torch/` (0 bytes, 0 files)  
  *Evidence:* Both folders exist as empty directories in `E:\FYP\cache\`.

### 8.3 Files in the Wrong Place
- **Audit Reports in Data Directory:**
  - `data/frames/out/REPORT.md`  
  *Evidence:* A Markdown report from an agent probe is saved inside the data frames output directory instead of `docs/`.
- **Benchmark Scripts in Evaluation Directory:**
  - `tools/env_audit/run_T2_process_a.sh` and `tools/env_audit/process_a_whisper.py` generate artifacts directly into `data/day04_batch_vs_online/eval/`.

### 8.4 Inconsistent Naming and Conventions
- **Documentation Filenames:**
  - `docs/Embedding Report.md` (Title case with space) vs `docs/OCR_report.md` (Snake_case with mixed caps).
- **Audit Task Script Naming:**
  - Tasks in `tools/env_audit/` alternate between `run_T*.py`, `verify_6*.py`, `smoke_*.py`, `check_*.py`, and `run_F*.py` without a clear taxonomy.

### 8.5 Mixed Concerns
- **Subproject Nesting in `embedding/`:**
  - `embedding/` contains its own `.venv/`, `.pytest_cache/`, `data/`, `requirements.lock.txt`, and `tools/`, functioning as an isolated project within the main project.
- **Storage and Code Colocation:**
  - Multi-gigabyte runtime binaries (`wsl/`, `docker/`, `cache/`, `LLMs/`) sit in the same root tree as source scripts and documentation.

### 8.6 Missing Pieces
- **Version Control:** No Git repository initialized; no `.gitignore` file.
- **Top-Level Package Structure:** No root `pyproject.toml`, `setup.py`, or Python package directory (no `insightex/` with `__init__.py`).
- **Project README:** No `README.md` exists in the repo root.
- **Target Pipeline Modules:** As noted in Section 4, zero code exists for the API server, database/graph store, query router, PDF chunker, or web user interfaces.

---

## 9. Open Questions for the Project Team

1. **Git Initialization & VCS Strategy:**  
   When Git is initialized, which directories will be permanently ignored? (Recommended for ignore: `wsl/`, `docker/`, `cache/`, `LLMs/`, `embedding/.venv/`, and `data/**/raw/`).
2. **Path Portability:**  
   `insightex_env.sh` and multiple scripts hardcode `/home/bilal_aamir/`. Will future execution standardize on dynamic `$HOME` resolution, or will the primary development username remain fixed?
3. **Status of `embedding/` Subdirectory:**  
   Is `embedding/tools/eval_embeddings/` intended to be refactored into a general `evaluation/` module, or should the bake-off code remain preserved exactly as an archival artifact?
4. **Visual Pipeline Gate:**  
   Given the 2 out of 5 hang rate documented in `OCR_report.md`, will the 30-frame bake-off for PaddleOCR-VL be conducted, or should the visual pipeline remain disabled for the initial baseline milestone?
5. **Textbook Selection for Feature 1 (Test B):**  
   Has an open-source or standard machine learning textbook PDF been selected for the timestamp-to-page fusion evaluation?
