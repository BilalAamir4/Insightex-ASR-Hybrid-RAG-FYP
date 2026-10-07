# Models

Table version of `config/models.yaml` (the registry is authoritative). Never choose a model whose status is `pending` or `undecided`; the user makes final model calls.

## Registry

| Key | Model | Runtime / device | Status | Peak VRAM (MiB) | Decision / notes |
|---|---|---|---|---|---|
| asr | faster-whisper (checkpoint not chosen; candidates `Systran/faster-whisper-medium`, `Systran/faster-whisper-large-v3`) | CTranslate2, CUDA fp16 | pending | not recorded (large-v3: 5,530 in the 10-minute run) | Waits on WER evaluation |
| llm | Ollama `qwen3.5:latest` (9.7B Q4_K_M, id `6488c96fa5fa`) | Ollama on Windows, CUDA | pending | 7,566 at `num_ctx` 8192 | Fallback candidate Gemma 4 E4B; unload with `keep_alive: 0` |
| embedding | `BAAI/bge-m3` (1024-d, 30 s windows) | sentence-transformers, CUDA | decided | 3,089 (standalone, measured 2 Oct 2026, not re-run) | `docs/reports/Embedding_Report.md`, `docs/adr/0001-bge-m3.md`. Rejected (tied): `Qwen/Qwen3-Embedding-0.6B` |
| reranker | none | none | undecided | n/a | Not yet evaluated |
| ocr_vlm | PaddleOCR-VL (0.9B), folder `PaddleOCR-VL-1.6` | Paddle, CUDA, `~/envs/paddleocr-vl` | optional | about 3,097 allocated; about 7,950 reserved by the allocator | `docs/reports/OCR_report.md`; gated on a 30-frame bake-off |

## Storage map

| What | Master / location | Runtime location |
|---|---|---|
| HuggingFace models (bge-m3, Qwen3-Embedding-0.6B, faster-whisper medium and large-v3) | `${INSIGHTEX_MODEL_CACHE_MASTER}/huggingface` (`/mnt/e/FYP/cache`) | `${HF_HOME}` (`~/cache/huggingface`, ext4) |
| Ollama models | `E:\FYP\LLMs` (Windows `OLLAMA_MODELS`) | served by Windows Ollama at `localhost:11434` |
| PaddleX / PaddleOCR-VL | `${INSIGHTEX_MODEL_CACHE_MASTER}/paddlex` (about 302 MB) | `~/.paddlex` (about 1,985 MB). The difference is unresolved. |
| Pip / torch caches | `${INSIGHTEX_MODEL_CACHE_MASTER}/pip` | `~/cache/pip`, `~/cache/torch` |

Do not point runtime caches at `/mnt/e` (DrvFS loads were measured 3.5x to 7.4x slower). Weights are never stored in the repo.

## VRAM budget (RTX 3070, 8,192 MiB)

Measured values from `docs/ENVIRONMENT.md` and the old `ENV_AUDIT_REPORT.md` (removed 2026-10-07, in git history). The Windows desktop holds about 1,000 MiB at idle.

| Stage | Peak (MiB) | Note |
|---|---|---|
| Whisper large-v3, 10 min | 5,530 | verified 3 Oct 2026 |
| Ollama qwen3.5, `num_ctx` 8192 | 7,566 | leaves 626 MiB |
| bge-m3 | 3,089 | earlier session, not re-run |
| PaddleOCR-VL | about 7,950 reserved (about 3,097 used) | allocator behaviour; 2 of 5 probe runs hung (`OCR_report.md`) |

Contract: never run two CUDA stages at once. Each stage is its own subprocess and exits fully before the next starts. Free VRAM first (`ollama ps`, then `ollama stop <model>`).
