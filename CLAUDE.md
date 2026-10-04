# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Insightex** is a final-year project: a timestamp-grounded knowledge base for code-switched (Urdu + English) lecture videos. The repo is currently at the **evaluation / environment-validation stage**: there is no pipeline application yet, only eval scripts, probes, audit tooling and reports. It is not a git repository.

Planned pipeline (each stage is a separate process; see the VRAM contract below):
FFmpeg audio extraction → faster-whisper (large-v3, `language="ur"`) transcription → Ollama `qwen3.5:latest` concept extraction (JSON Schema output) → BGE-M3 embeddings → hybrid retrieval (NetworkX knowledge graph + FAISS flat IP index, behind a router). An optional visual pipeline (scene detection + PaddleOCR-VL) sits behind a `visual.enabled` flag. ASR is the committed baseline; the visual pipeline must never block a baseline milestone.

## Layout

- `docs/`: decision records. `Embedding Report.md` (model and chunk choice) and `OCR_report.md` (PaddleOCR-VL feasibility). Read these before changing anything they cover.
- `tools/env_audit/`: environment audit scripts (`run_*`, `verify_*`, `smoke_*`, `check_*`) and `ENV_AUDIT_REPORT.md`, the most recent authoritative record of the environment, measured VRAM and the Ollama request contract.
- `embedding/tools/eval_embeddings/`: the embedding bake-off (`embed_bakeoff.py`, `test_bakeoff.py`, `queries.csv`, `selftest/` synthetic fixture).
- `tools/vl_probe/`: PaddleOCR-VL probe (`probe.py`, driven from Windows by `run_probe.ps1`).
- `data/day04_batch_vs_online/`: the single test lecture (raw mp4, eval WAVs, Whisper SRT/JSON, manual Roman-Urdu reference).
- `cache/`, `LLMs/` (Ollama models via `OLLAMA_MODELS`), `wsl/`, `docker/`: large binary stores. Do not search, modify or delete them.

## Environment (WSL2 Ubuntu-24.04 + Windows host)

- Python work runs **inside WSL** (`/mnt/e/FYP` = `E:\FYP`). Main venv: `~/envs/insightex` (Python 3.12, torch cu128, faster-whisper, sentence-transformers, faiss-cpu, networkx), pinned in `requirements.lock.txt`. PaddleOCR has its own venv, `~/envs/paddleocr-vl`. `embedding/.venv` is the older bake-off venv, superseded by `~/envs/insightex`.
- **Always launch GPU work through the wrapper**, otherwise faster-whisper fails at inference time (not import time) with `libcublas.so.12 is not found`:
  ```bash
  bash /mnt/e/FYP/tools/env_audit/run_in_env.sh python <script.py> ...
  ```
  It sources `env/insightex_env.sh` (sets `HF_HOME`, `HF_HUB_OFFLINE=1`, `TORCH_HOME`, `OLLAMA_BASE_URL`, and CUDA `LD_LIBRARY_PATH` from the venv's `nvidia-*` packages) and activates the venv.
- Run commands from a WSL shell rather than nesting them through PowerShell (`wsl -- bash -lc "..."`), because quoting breaks `$` and `&&`.
- **Model caches:** the runtime cache is on ext4 (`~/cache/huggingface`), and `E:\FYP\cache` is the master copy. Do not point caches at `/mnt/e` (DrvFS loads are 3.5–7x slower; this was rejected). `HF_HUB_OFFLINE=1` is global. To add a model: download with `HF_HUB_OFFLINE=0 HF_HOME=/mnt/e/FYP/cache/huggingface`, `cp -ru` it into `~/cache/huggingface/hub/`, then verify hashes with `tools/env_audit/run_F7_check.py`.
- **Ollama** runs on the Windows host, bound to `127.0.0.1:11434` (reached from WSL as `localhost` via mirrored networking). Never set `OLLAMA_HOST=0.0.0.0`. Start it with `tools/env_audit/start_ollama.ps1`.
- Storage rule: everything project-related lives under `E:\FYP` and nothing should grow on C:.

## GPU / VRAM contract (RTX 3070, 8 GB)

- Never run two CUDA stages at once. Each stage runs as its own subprocess and exits fully before the next one starts. Ollama alone peaks at about 7.5 GB.
- Before any GPU run, free VRAM: `ollama ps`, then `ollama stop <model>`.
- Ollama batch calls: `/api/chat` with a JSON Schema `format`, `think: false`, `keep_alive: "10m"`, `num_ctx: 8192`, `temperature: 0.1`, `num_predict: 600`. At the end of a batch, unload with `keep_alive: 0` in a `finally` block and poll `ollama ps` until the model is gone. The full request body is in `ENV_AUDIT_REPORT.md` §6.5.

## Embedding bake-off commands

Run these from `/mnt/e/FYP/embedding`:

```bash
# Unit tests (no GPU or model needed)
python -m pytest tools/eval_embeddings/test_bakeoff.py
python -m pytest tools/eval_embeddings/test_bakeoff.py::test_overlap_hit_rule   # single test

# Dry run with the deterministic fake embedder (no download, no GPU)
python tools/eval_embeddings/embed_bakeoff.py --srt tools/eval_embeddings/selftest/fake_transcript.srt \
  --queries tools/eval_embeddings/selftest/fake_queries.csv --out /tmp/dry --dry-run

# Reproduce the final run (always pass --max-seq-length 1024; the 512 default truncates Qwen3 windows)
HF_HUB_OFFLINE=1 python tools/eval_embeddings/embed_bakeoff.py \
  --srt data/day04_batch_vs_online/whisper_urdu.srt --queries tools/eval_embeddings/queries.csv \
  --out tools/eval_embeddings/results_seq1024 --max-seq-length 1024
```

Other flags: `--models bge-m3,qwen3-0.6b`, `--windows 30,60,90`, `--stride`, `--topk`, `--batch-size`.

## Decisions already made (don't relitigate without new evidence)

- Embedding model: **`BAAI/bge-m3`** (tied with Qwen3-Embedding-0.6B, chosen on tie-breaks: sparse weights for the router and lower VRAM). Chunking: **30-second non-overlapping windows** of native-script Whisper text, not single SRT lines. Never embed Roman Urdu; it is only for WER evaluation.
- Bake-off semantics: a hit means the retrieved window *strictly overlaps* the labelled range. Qwen3 gets an instruction prefix on the query side only. Embeddings are L2-normalised and searched with `IndexFlatIP`.
- Use only `results_seq1024/` numbers. `results/` (the 512-token run) and its `analysis.md` are outdated.
- Still open: Test B (concept → textbook page, ±2 pages; blocked until a textbook is chosen), Test C (English concept summaries; needs Ollama extraction), and reranker choice (should match the embedding family).

## Working norms from the project history

- Trust output files over chat summaries; earlier agent summaries misreported numbers. Recompute derived figures from the files and tie every number to its window, model and run.
- Ask before downloads, `sudo`, torch installs or stopping Ollama.
- Do not generate labelled query ranges from the SRT (that makes the evaluation circular), and do not describe labels as "hand-labelled" or "spot-checked" unless the user confirms it. Verify on the synthetic `selftest/` fixture, not the real lecture.
- Recommend; the user makes final model and design calls. State the limits honestly, mark unverified claims as such, and label carried-over measurements as not re-run.
