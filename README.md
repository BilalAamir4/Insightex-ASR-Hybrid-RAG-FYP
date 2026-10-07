# Insightex

A timestamp-grounded knowledge base for code-switched (Urdu + English) lecture videos. Final-year project.

**Stage:** evaluation and environment validation done; the backend is a skeleton (`backend/src/insightex/`, no pipeline code yet).

Planned pipeline (each stage is a separate process, one CUDA model at a time):
FFmpeg audio extraction, faster-whisper transcription (`language="ur"`), Ollama `qwen3.5:latest` concept extraction (JSON Schema output), BGE-M3 embeddings, hybrid retrieval (NetworkX graph + FAISS flat inner-product index, behind a router). An optional visual pipeline (scene detection + PaddleOCR-VL) sits behind `visual.enabled`. ASR is the committed baseline; the visual pipeline never blocks a baseline milestone.

## Quickstart (WSL2 Ubuntu-24.04)

Prerequisites: WSL2 Ubuntu-24.04, ffmpeg, the venv `~/envs/insightex` (Python 3.12) and, for LLM work, Ollama running on the Windows host (`scripts/windows/start_ollama.ps1`, `127.0.0.1:11434`). Setup detail: [docs/runbooks/setup.md](docs/runbooks/setup.md).

Run the commands below from the repo root (the directory that holds `pyproject.toml`).

```bash
source env/insightex_env.sh            # already sourced from ~/.profile after setup
source ~/envs/insightex/bin/activate
pip install -e . --no-deps             # installs the package and the `insightex` command; dependencies come from requirements.lock.txt

pytest                                 # offline suites; network tests: pytest -m network
bash scripts/test_frontend.sh          # frontend tests (Deno)
python -m insightex.api                # API + UI on http://127.0.0.1:8000
insightex config show                  # effective settings, each value tagged with its source
insightex config validate              # exit 0 if the configuration loads
```

GPU work always goes through the wrapper (otherwise faster-whisper fails at inference with `libcublas.so.12 not found`): `bash scripts/run_in_env.sh python <script.py> ...`. Free VRAM before any GPU run (`ollama ps`, `ollama stop <model>`).

## Configuration

Every setting and its default is in [config/default.yaml](config/default.yaml), validated by typed models in `backend/src/insightex/core/config.py`; an unknown key or a wrong type fails at startup. Override only what you change, in `config/local.yaml` (gitignored; see `config/local.example.yaml`). Library and process variables (`HF_HOME`, `LD_LIBRARY_PATH`, ...) stay in `env/insightex_env.sh`. Precedence, lowest to highest:

1. `config/default.yaml`
2. the local file: `$INSIGHTEX_CONFIG` if set (must exist), otherwise `config/local.yaml` if present
3. environment variables `INSIGHTEX__<SECTION>__<KEY>`, e.g. `INSIGHTEX__API__PORT=8001` (`INSIGHTEX_DATA` and `OLLAMA_BASE_URL` stay valid aliases)
4. explicit overrides passed to `load_settings(overrides)` (tests, CLI flags)

## Layout

| Path | Contents |
|---|---|
| `backend/` | Package skeleton `insightex` and test folders |
| `workers/ocr/` | Optional PaddleOCR-VL worker (README only) |
| `frontend/` | Placeholder |
| `tools/` | Standalone tools (never import from `backend/`): probes, benchmarks, env checks |
| `scripts/` | `run_in_env.sh`, `verify_env.sh`, `windows/` PowerShell helpers |
| `config/` | `default.yaml` (all settings), `local.example.yaml`, `models.yaml` (model registry), `local.yaml` (gitignored) |
| `env/` | `insightex_env.sh` (canonical env script), `.env.example` |
| `docs/` | Models, ADRs, contracts, reports, runbooks, proposal |

Runtime data lives outside the repo in `~/insightex-data` (`$INSIGHTEX_DATA`): test lecture, eval files, logs. Heavy storage (model caches, Ollama models, VHDX files) stays under `E:\FYP` and is never in this repo.

## Docs

- [docs/MODELS.md](docs/MODELS.md): model registry, storage map, VRAM budget
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md): current environment state and how to verify it
- [docs/adr/](docs/adr/README.md): architecture decision records (index, template, rules)
- [docs/reports/](docs/reports/): embedding report, OCR report, environment audit, migration report
- [docs/runbooks/setup.md](docs/runbooks/setup.md), [docs/runbooks/after_restart_checklist.md](docs/runbooks/after_restart_checklist.md)
- [CLAUDE.md](CLAUDE.md): project rules for Claude Code
