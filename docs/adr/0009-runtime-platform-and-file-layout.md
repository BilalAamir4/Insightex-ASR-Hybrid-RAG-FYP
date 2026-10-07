# ADR-0009: Runtime platform and file layout

Status: Accepted
Date decided: not recorded; on or before 2026-10-04
Date recorded: 2026-10-08
Module: M0

## Context

The project runs on a Windows 11 host (RTX 3070, 8 GB VRAM) with the GPU libraries and models needed for ASR, embeddings and a local LLM. Reading model files across the WSL 9P/drvfs bridge from `/mnt/e` was measured 3.5 to 7.4 times slower than ext4 (carried over from the earlier audit, not re-run).

## Decision

- WSL2 Ubuntu 24.04 with its disk image on E: (`E:\FYP\wsl\Ubuntu-24.04`).
- venv `~/envs/insightex` on WSL ext4. Code at `~/insightex` (git). Runtime data at `~/insightex-data`.
- `E:\FYP` keeps heavy storage: the WSL disk, Docker data, the master model cache `E:\FYP\cache` and the Ollama models `E:\FYP\LLMs`. It also holds the original files as backup. `E:\FYP\env` is backup only.
- Runtime Hugging Face models are copied to `~/cache/huggingface` on ext4. `HF_HUB_OFFLINE=1`.
- Env script `env/insightex_env.sh` (once-per-shell guard), sourced from `~/.profile` and from the venv activate script.
- Key versions: torch 2.11.0+cu128, faster-whisper 1.2.1, ctranslate2 4.8.2, sentence-transformers 6.1.0, transformers 5.18.0, faiss-cpu 1.15.1, networkx 3.6.1. Native FFmpeg 6.1.1 in WSL.

## Alternatives considered

Symlinking WSL caches (`~/.paddlex`, `~/.cache/pip`) into `/mnt/e`: rejected, because it reintroduces the slow 9P path.

## Consequences

- Nothing project-related grows on C:.
- Adding a model means downloading to the master cache and copying it to `~/cache/huggingface`.
- `tools/verify_env.py` fails if a cache resolves into `/mnt`.

## Evidence

- `docs/ENVIRONMENT.md` (storage layout, env script, versions; last verified 2026-10-07).
- `env/insightex_env.sh`; `scripts/verify_env.sh`.
- M0 closed 2026-10-07: `scripts/verify_env.sh` passes 12/12 (`$INSIGHTEX_DATA/env_reports/20261007T233720.json`).

## Gate / revisit when

Revisit when the host, the WSL distribution or the storage layout changes.
