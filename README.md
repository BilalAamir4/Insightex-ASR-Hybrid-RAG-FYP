# Insightex

A timestamp-grounded knowledge base for code-switched (Urdu + English) lecture videos. Final-year project.

**Stage:** evaluation and environment validation done; the backend is a skeleton (`backend/src/insightex/`, no pipeline code yet).

Planned pipeline (each stage is a separate process, one CUDA model at a time):
FFmpeg audio extraction, faster-whisper transcription (`language="ur"`), Ollama `qwen3.5:latest` concept extraction (JSON Schema output), BGE-M3 embeddings, hybrid retrieval (NetworkX graph + FAISS flat inner-product index, behind a router). An optional visual pipeline (scene detection + PaddleOCR-VL) sits behind `visual.enabled`. ASR is the committed baseline; the visual pipeline never blocks a baseline milestone.

## Quickstart (WSL2 Ubuntu-24.04)

```bash
cd ~/insightex
# GPU work always goes through the wrapper (otherwise faster-whisper fails at inference with libcublas.so.12 not found)
bash scripts/run_in_env.sh python <script.py> ...
```

Ollama runs on the Windows host (`scripts/windows/start_ollama.ps1`), bound to `127.0.0.1:11434`. Free VRAM before any GPU run (`ollama ps`, `ollama stop <model>`).

## Layout

| Path | Contents |
|---|---|
| `backend/` | Package skeleton `insightex` and test folders |
| `workers/ocr/` | Optional PaddleOCR-VL worker (README only) |
| `frontend/` | Placeholder |
| `tools/` | Standalone tools (never import from `backend/`): probes, benchmarks, env checks |
| `scripts/` | `run_in_env.sh`, `verify_env.sh`, `windows/` PowerShell helpers |
| `config/` | `default.yaml`, `models.yaml` (model registry), `local.yaml` (gitignored) |
| `env/` | `insightex_env.sh` (canonical env script), `.env.example` |
| `docs/` | Models, ADRs, contracts, reports, runbooks, proposal |

Runtime data lives outside the repo in `~/insightex-data` (`$INSIGHTEX_DATA`): test lecture, eval files, logs. Heavy storage (model caches, Ollama models, VHDX files) stays under `E:\FYP` and is never in this repo.

## Docs

- [docs/MODELS.md](docs/MODELS.md): model registry, storage map, VRAM budget
- [docs/adr/0001-bge-m3.md](docs/adr/0001-bge-m3.md): embedding model and window decision
- [docs/reports/](docs/reports/): embedding report, OCR report, environment audit, migration report
- [docs/runbooks/setup.md](docs/runbooks/setup.md), [docs/runbooks/after_restart_checklist.md](docs/runbooks/after_restart_checklist.md)
- [CLAUDE.md](CLAUDE.md): project rules for Claude Code
