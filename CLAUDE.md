# CLAUDE.md

Guidance for Claude Code in this repository. This file loads at the start of every session, so it stays short (target under 150 lines). More detail lives in places that load only when needed:
- `.claude/rules/*.md`: path-scoped rules. Each one loads only when you touch files matching its `paths:` globs.
- Nested `CLAUDE.md` files (e.g. `tools/CLAUDE.md`). These load when you work in that folder.
- `docs/features/` <!-- TODO: not yet in repo -->, `docs/adr/` and `docs/reports/`. Read these on demand.

## What this is

**Insightex** is a final-year project (Bilal Aamir and Fatima Asad, Bahria University Islamabad). It is a timestamp-grounded knowledge base for code-switched Urdu/English lecture videos. A student or teacher asks a question and gets an answer whose citations seek the video to the right moment.

- The **ASR pipeline is the committed Baseline.**
- The **visual pipeline** (scene detection + OCR) is Optional. It sits behind `visual.enabled`, is time-boxed, and must never block a Baseline milestone.
- Feature numbers (F1–F20) follow the proposal. Tiers and per-feature notes are in `docs/features/`. <!-- TODO: not yet in repo -->

## Current state (update this block at every milestone)

- **Phase 0 (Foundation).** The build plan is in `docs/BUILD_ORDER.md` (modules M0–M20, each with exit criteria). <!-- TODO: not yet in repo -->
- **Done:** M3 link ingestion (6 Oct 2026). This covers the engine + CLI, the FastAPI API with one-worker background jobs, and the static HTML ingest/library/player page.
- **Partial:**
  - M0b: repo and tag `import-baseline` exist. Config system, ADRs and textbook choice are still to do.
  - M1: background jobs exist. GPU lease, resume-after-kill and a generic stage runner are still to do.
  - M2: the normalisation path exists. Local file upload is still to do.
  - M6: API, player and `seekTo(seconds)` exist. Ask box and citations are still to do.
- **Not started:** the ASR stage (M4), production embeddings/FAISS (M5), concept extraction, the graph, the router and answers.
- Before starting a module, check its open decisions in `docs/BUILD_ORDER.md` ("Pending decisions by module"). Settle them before building. <!-- TODO: not yet in repo -->

## Pipeline (target)

Each stage runs as its own process (see the GPU contract below).

ingest (URL or upload) → ffmpeg normalise → faster-whisper ASR → 30 s windows → BGE-M3 dense + sparse → FAISS `IndexFlatIP`
                                                        ↘ Ollama concept extraction (JSON Schema) → canonicalise → NetworkX graph
query → router (graph-first on known concept labels, otherwise vector or merge) → grounded answer with validated citations → `seekTo(seconds)`

Per-lecture workspace: `$INSIGHTEX_DATA/lectures/<lecture_id>/`. It holds `video.mp4`, `audio.wav` (16 kHz mono), `thumbnail.jpg` and `manifest.json` (schema v2). Later stages add their outputs here and record them in the manifest.

## Commands

```bash
# Every Python/GPU command goes through the wrapper. It sets the env and CUDA libs and activates the venv.
bash ~/insightex/scripts/run_in_env.sh python <script.py> ...
# Without the wrapper, faster-whisper fails at INFERENCE time with "libcublas.so.12 is not found".

# API + UI (binds 127.0.0.1:8000; host/port from `api:` in config/default.yaml)
bash ~/insightex/scripts/run_in_env.sh python -m insightex.api
# Backend tests (offline suites; network tests only with `pytest -m network`)
bash ~/insightex/scripts/run_in_env.sh pytest
# Frontend tests (Deno from the venv)
bash ~/insightex/scripts/test_frontend.sh
```

Run commands from a WSL shell. Do not nest them through PowerShell (`wsl -- bash -lc "..."`), because quoting breaks `$` and `&&`.

## Environment (short version; full detail in `docs/reports/ENV_AUDIT_REPORT.md`)

- WSL2 Ubuntu-24.04 runs on a Windows host. `/mnt/e/FYP` is `E:\FYP`. The repo is `~/insightex`, runtime data is `~/insightex-data`, and both sit on the ext4 vhdx stored on `E:\FYP\wsl`.
- Main venv: `~/envs/insightex` (Py 3.12, torch cu128). It is pinned in `requirements.lock.txt`. PaddleOCR has its own venv, `~/envs/paddleocr-vl`.
- `env/insightex_env.sh` sets `INSIGHTEX_HOME`, `INSIGHTEX_DATA`, `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE=1`, `TORCH_HOME`, `OLLAMA_BASE_URL` and CUDA `LD_LIBRARY_PATH`.
- The runtime HF cache is `~/cache/huggingface` (ext4). The master copy is `E:\FYP\cache`.
  - **Never point caches at `/mnt/e`.** DrvFS loads are 3.5–7x slower; this was tested and rejected.
  - To add a model: download it with `HF_HUB_OFFLINE=0 HF_HOME=$INSIGHTEX_MODEL_CACHE_MASTER/huggingface`, `cp -ru` it into `~/cache/huggingface/hub/`, then verify with `tools/audit_env/run_F7_check.py`.
- Ollama runs on Windows at `127.0.0.1:11434`. WSL reaches it as `localhost` through mirrored networking.
  - **Never set `OLLAMA_HOST=0.0.0.0`.**
  - Start it with `scripts/windows/start_ollama.ps1`.
- Do not search, modify or delete `E:\FYP\cache`, `E:\FYP\LLMs`, `E:\FYP\wsl` or `E:\FYP\docker`. The original pre-migration files on `E:\FYP` are the backup.
- Nothing project-related should grow on C:.
- Note: `ENV_AUDIT_REPORT.md` §1–5 still describe an older audit that includes rejected fixes, until M0 rewrites the report. Use §6+ and this file instead.

## GPU / VRAM contract (RTX 3070, 8 GB) — hard rules

- Never run two CUDA stages at once. Each stage is its own subprocess and must exit fully before the next one starts.
- Ollama (`qwen3.5:latest`) alone peaks at about 7.7–7.8 GB, which leaves roughly 450 MiB. Always set `num_ctx` explicitly.
- Before any GPU run, check `ollama ps`, then run `ollama stop <model>` if a model is loaded. Ask the user before stopping Ollama.
- Ollama batch call body: `/api/chat` with a JSON Schema `format`, `think: false`, `keep_alive: "10m"`, `num_ctx: 8192`, `temperature: 0.1` and `num_predict: 600`.
  - In a `finally` block, unload with `keep_alive: 0`, then poll `ollama ps` until the model is gone.
  - The full body is in `ENV_AUDIT_REPORT.md` §6.5.
- Query time (planned, M5): the GPU belongs to Ollama. BGE-M3 query encoding and the reranker run on CPU inside the API process.

## Decisions already made (don't relitigate without new evidence)

Each decision has, or will get, an ADR in `docs/adr/`. Decision records are in `docs/reports/`.

- **Embeddings:** `BAAI/bge-m3`, on 30 s non-overlapping windows of native-script Whisper text. Never embed Roman Urdu; it is used only for WER.
- **Retrieval:** L2-normalised embeddings searched with `IndexFlatIP`. A hit means the retrieved window strictly overlaps the labelled range.
- **Bake-off numbers:** use only `docs/reports/embedding_bakeoff/results_seq1024/`. When re-running, pass `--max-seq-length 1024`. Older artefacts are in tag `import-baseline`.
- **Link ingestion:** a single path for every source, which is to download fully and play locally (no embedded YouTube player).
- **Infrastructure:** no Celery, Redis, Docker Compose or Neo4j until the core pipeline is validated. Use SQLite jobs with one worker.
- Read `docs/reports/Embedding_Report.md` and `docs/reports/OCR_report.md` before changing anything they cover.
- **Still open:** Whisper checkpoint and language setting (M4), LLM choice (qwen3.5 vs Gemma 4 E4B, M7), textbook (M0b), reranker, Test B and Test C.

## Working norms

- Production code goes in `backend/src/insightex/` (workers in `workers/`, UI in `frontend/`). Diagnostic and benchmark scripts go in `tools/`; they are standalone and must never import from `backend/`.
- Trust output files over chat summaries, because earlier agent summaries misreported numbers. Recompute derived figures from the files, and tie every number to its window, model and run.
- Ask before downloads, `sudo`, torch installs or stopping Ollama.
- Do not generate labelled query ranges from the SRT, because that makes the evaluation circular.
  - Do not call labels "hand-labelled" or "spot-checked" unless the user confirms it.
  - Verify on synthetic fixtures, not on the real lecture.
- Recommend, but let the user make final model and design calls.
  - State limits honestly and mark unverified claims as unverified.
  - Label carried-over measurements as not re-run.
  - Frame risky technical claims as decision gates with a measurable exit, not as assertions.
- Git: do not add a Claude co-author trailer to commits.

## Where to look

| Need | File |
|---|---|
| Directory map | `README.md` |
| Models, storage map, VRAM budget | `docs/MODELS.md` |
| Build plan, exit criteria, pending decisions | `docs/BUILD_ORDER.md` <!-- TODO: not yet in repo --> |
| Per-feature spec (F1–F20) | `docs/features/Fxx-*.md` <!-- TODO: not yet in repo --> |
| Why a decision was made | `docs/adr/`, `docs/reports/` |
| ADRs (so far `0001-bge-m3.md`: embedding model and window) | `docs/adr/` |
| Draft JSON Schema: Ollama concept-extraction output (`concepts[]` with name, description, exam_relevant) | `docs/contracts/extraction.json` |
| Draft JSON Schema: ASR segment list (id, start, end, text, avg_logprob, no_speech_prob) | `docs/contracts/segments.json` |
| Setup and after-restart steps | `docs/runbooks/setup.md`, `docs/runbooks/after_restart_checklist.md` |
| Proposal, feature list (placeholder; documents not added yet) | `docs/proposal/README.md` |
| Reports: `Embedding_Report`, `OCR_report`, `vl_probe_REPORT`, `ENV_AUDIT_REPORT`, `PRE_MIGRATION_AUDIT`, `MIGRATION_REPORT` | `docs/reports/` |
| Test lecture (mp4, WAVs, SRT/JSON, Roman-Urdu reference, queries) | `~/insightex-data/eval/day04_batch_vs_online/` |