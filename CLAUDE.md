# CLAUDE.md

Guidance for Claude Code in this repository. This file loads at the start of every session, so it stays short (target under 150 lines). More detail lives in places that load only when needed:
- `.claude/rules/*.md`: path-scoped rules. Each one loads only when you touch files matching its `paths:` globs.
- Nested `CLAUDE.md` files (e.g. `tools/CLAUDE.md`). These load when you work in that folder.
- `docs/features/`, `docs/adr/` and `docs/reports/`. Read these on demand.

## What this is

**Insightex** is a final-year project (Bilal Aamir and Fatima Asad, Bahria University Islamabad). It is a timestamp-grounded knowledge base for code-switched Urdu/English lecture videos. A student or teacher asks a question and gets an answer whose citations seek the video to the right moment.

- The **ASR pipeline is the committed Baseline.**
- The **visual pipeline** (scene detection + OCR) is Optional. It sits behind `visual.enabled`, is time-boxed, and must never block a Baseline milestone.
- Feature numbers (F1–F20) follow the proposal. Tiers and per-feature notes are in `docs/features/`.

## Current state (update this block at every milestone)

- **Phase 0 (Foundation) complete; M1 to M4 complete; Phase 1 continues with M5 (windows, embeddings, FAISS).** The build plan is in `docs/BUILD_ORDER.md` (modules M0–M20, each with exit criteria).
- **Done:**
  - M4 ASR stage (10 Oct 2026): `asr` runs after `normalise` in both ingest pipelines. Whisper large-v3 runs in a subprocess per job under the GPU lease and writes `transcript.json` and `transcript.vtt` (schema `docs/contracts/transcript.schema.json`; the VTT is a developer check only). **Every submission needs a language** (CLI `--language`, link API `language`, upload header `X-Insightex-Language`, a required dropdown): chosen per lecture from `config/languages.yaml`, no default, no auto-detect (ADR-0040). Hindi (Whisper code `ur`, evidence ADR-0039) is the only tested language; all others are untested and shown with an "Untested language" badge; untested lectures are excluded from thesis evaluation numbers. Users read English only; transcripts are internal and never shown (ADR-0041). Stage design: ADR-0042. `tools/m4_verify` 12/12 (Day 4: 351 segments identical to the gate, RTF 0.113, peak 4,523 MiB above baseline); evidence `docs/evidence/m4/`.
  - M2 upload ingestion (10 Oct 2026): `insightex ingest-file` (CLI) and `POST /api/ingest/upload` (raw streamed body, ADR-0037) feed one shared normalisation engine (`normalise_media`, `NORMALISER_VERSION` 4) that link ingestion also uses. Validation and the closed error-code table are in ADR-0036. The A/V sync invariant is in ADR-0038 (see "Decisions already made"). `tools/m2_verify` 13/13 on the Day 4 lecture; the by-hand browser checklist passed after the ADR-0038 fix. Evidence: `docs/evidence/m2/`.
  - M1 core (9 Oct 2026): SQLite job queue + single worker with crash recovery and resume, GPU lease, workspaces with chained stage keys and a cache index with eviction (ADR-0033 to ADR-0035). Link ingestion runs on the runner as the `ingest_link` pipeline (`fetch`, `normalise`); the API exposes jobs, Server-Sent Events progress, the library and delete (`docs/contracts/api.md`). One job system, one workspace layout (`$INSIGHTEX_DATA/workspaces/`). Lectures in the old `lectures/` folder are not read and must be re-ingested. Evidence: `docs/evidence/m1/`.
  - M0b repo scaffold, typed config and decision log (8 Oct 2026): `config/default.yaml`, `insightex config show|validate`, commit-msg hook, ADRs in `docs/adr/` (decision log: `docs/adr/README.md`), textbook chosen (ADR-0029: Géron, Hands-On Machine Learning, 2nd Edition). Repo and tag `import-baseline` exist.
  - M0 environment verification (7 Oct 2026): cold-boot pass, `scripts/verify_env.sh` 12/12 after a full Windows restart with Ollama started by Task Scheduler. State in `docs/ENVIRONMENT.md`, Ollama contract in `docs/adr/0002-ollama-call-contract.md`.
  - M3 link ingestion (6 Oct 2026), moved onto the runner in M1.
- **Partial:**
  - M6: API, player, upload form and `seekTo(seconds)` exist. Ask box and citations are still to do.
- **Not started:** production embeddings/FAISS (M5), concept extraction, the graph, the router and answers.
- **Before any further WER gate (language promotion, ADR-0040):** re-ingest the eval lectures through normaliser v4. Older `audio.wav` files predate the start-offset padding, so their timings may be shifted. Lectures added before M4 session 2 have no transcript and show "Not transcribed"; add them again with a language.
- Before starting a module, check its open decisions in `docs/BUILD_ORDER.md` ("Pending decisions by module"). Settle them before building.

## Pipeline (target)

Each stage runs as its own process (see the GPU contract below).

ingest (URL or upload, with the lecture's language) → fetch → ffmpeg normalise → asr (faster-whisper) → 30 s windows → BGE-M3 dense + sparse → FAISS `IndexFlatIP`
                                                        ↘ Ollama concept extraction (JSON Schema) → canonicalise → NetworkX graph
query → router (graph-first on known concept labels, otherwise vector or merge) → grounded answer with validated citations → `seekTo(seconds)`

Per-video workspace: `$INSIGHTEX_DATA/workspaces/<workspace_id>/` (`yt-<id>` or `sha256-<32 hex>`), with `manifest.json` and `stages/<stage>/<key>/` per completed stage (`video.mp4`, `audio.wav`, `thumbnail.jpg` and `normalise.json` come from `normalise`; `source.json` describes the source). Later stages add their outputs here; `asr` adds `transcript.json` (the source of truth) and `transcript.vtt`. Find files with `Workspaces.stage_output_dir`.

## Commands

```bash
# Every Python/GPU command goes through the wrapper. It sets the env and CUDA libs and activates the venv.
bash ~/insightex/scripts/run_in_env.sh python <script.py> ...
# Without the wrapper, faster-whisper fails at INFERENCE time with "libcublas.so.12 is not found".

# Worker (background) + API + UI together (binds 127.0.0.1:8000; host/port from `api:` in config/default.yaml)
bash ~/insightex/scripts/dev_run.sh
# The worker is a separate process: `insightex worker`; `insightex gpu status`, `insightex cache list|pin|delete|gc`, `insightex jobs list|show`
# Ingest a local file: `insightex ingest-file <path> --confirm-rights --language <id> [--wait]` (exit 0 ok/deduplicated, 2 rejected, 1 internal error); ids: `insightex languages list`
# API alone (jobs only run while a worker runs): bash ~/insightex/scripts/run_in_env.sh python -m insightex.api
# Backend tests (offline suites; network tests only with `pytest -m network`; media fixtures only with `-m media`)
bash ~/insightex/scripts/run_in_env.sh pytest
# Frontend tests (Deno from the venv)
bash ~/insightex/scripts/test_frontend.sh
# Lint (ruff pinned in the `dev` extra: pip install -e '.[dev]'); tools/ still has pre-existing findings
bash ~/insightex/scripts/run_in_env.sh ruff check
```

Run commands from a WSL shell. Do not nest them through PowerShell (`wsl -- bash -lc "..."`), because quoting breaks `$` and `&&`.

## Environment (short version; full detail in `docs/ENVIRONMENT.md`)

- WSL2 Ubuntu-24.04 runs on a Windows host. `/mnt/e/FYP` is `E:\FYP`. The repo is `~/insightex`, runtime data is `~/insightex-data`, and both sit on the ext4 vhdx stored on `E:\FYP\wsl`.
- Main venv: `~/envs/insightex` (Py 3.12, torch cu128). It is pinned in `requirements.lock.txt`. PaddleOCR has its own venv, `~/envs/paddleocr-vl`.
- `env/insightex_env.sh` sets `INSIGHTEX_HOME`, `INSIGHTEX_DATA`, `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE=1`, `TORCH_HOME`, `OLLAMA_BASE_URL` and CUDA `LD_LIBRARY_PATH`.
- The runtime HF cache is `~/cache/huggingface` (ext4). The master copy is `E:\FYP\cache`.
  - **Never point caches at `/mnt/e`.** DrvFS loads are 3.5–7x slower; this was tested and rejected.
  - To add a model: download it with `HF_HUB_OFFLINE=0 HF_HOME=$INSIGHTEX_MODEL_CACHE_MASTER/huggingface`, `cp -ru` it into `~/cache/huggingface/hub/`, then verify with `tools/audit_env/run_F7_check.py`.
- Ollama runs on Windows at `127.0.0.1:11434`. WSL reaches it as `localhost` through mirrored networking.
  - **Never set `OLLAMA_HOST=0.0.0.0`.**
  - It starts automatically at Windows logon (Task Scheduler task `Insightex Ollama` runs `E:\FYP\start_ollama.ps1`; loopback only). If it is down, start that script by hand.
- Do not search, modify or delete `E:\FYP\cache`, `E:\FYP\LLMs`, `E:\FYP\wsl` or `E:\FYP\docker`. The original pre-migration files on `E:\FYP` are the backup.
- Nothing project-related should grow on C:.

## GPU / VRAM contract (RTX 3070, 8 GB) — hard rules

- Never run two CUDA stages at once. Each stage is its own subprocess and must exit fully before the next one starts.
- Ollama (`qwen3.5:latest`) alone peaks at about 7.4 GB at `num_ctx` 8192 (measured 2026-10-07), leaving 510 to 818 MiB depending on the Windows desktop's VRAM use (`docs/ENVIRONMENT.md`). Always set `num_ctx` explicitly; 16384 spills to CPU.
- Before any GPU run, check `ollama ps`, then run `ollama stop <model>` if a model is loaded. Ask the user before stopping Ollama.
- Unloading the model through the GPU lease (ADR-0033) is the approved way to free VRAM and needs no confirmation; stopping the Ollama service still does.
- Ollama calls go through `insightex.llm.ollama_client.chat_json`: `/api/chat` with a JSON Schema `format`, `think: false`, `keep_alive: "10m"`, `num_ctx` required (default 8192), `temperature` 0, `num_predict` explicit (default 1024).
  - Estimated prompt tokens + `num_predict` must fit in `num_ctx`; `done_reason: length` is an error, never parsed.
  - In a `finally` block, call `unload()` (`keep_alive: 0`, then poll `/api/ps` until the model is gone).
  - Full contract and measurements: `docs/adr/0002-ollama-call-contract.md`.
- Query time (planned, M5): the GPU belongs to Ollama. BGE-M3 query encoding and the reranker run on CPU inside the API process.
- Normalisation (ffmpeg, libx264) is CPU-only and takes no GPU lease.

## Decisions already made (don't relitigate without new evidence)

Each decision has an ADR in `docs/adr/` (index: `docs/adr/README.md`, the decision log). Decision records are in `docs/reports/`.

- **Embeddings:** `BAAI/bge-m3`, on 30 s non-overlapping windows of native-script Whisper text. Never embed Roman Urdu; it is used only for WER.
- **Retrieval:** L2-normalised embeddings searched with `IndexFlatIP`. A hit means the retrieved window strictly overlaps the labelled range.
- **Bake-off numbers:** use only `docs/reports/embedding_bakeoff/results_seq1024/`. When re-running, pass `--max-seq-length 1024`. Older artefacts are in tag `import-baseline`.
- **Link ingestion:** a single path for every source, which is to download fully and play locally (no embedded YouTube player). Link sources are kept after normalising (ADR-0035); uploaded originals are deleted unless `ingest.file.keep_original`.
- **Media normalisation (ADR-0036 to ADR-0038):** every source goes through `normalise_media`. Never add a second normalisation path.
  - `audio.wav` (16 kHz mono) is always derived from `video.mp4` with start padding, never from the source, so transcript time equals player time.
  - `video.mp4` must stay within one frame of A/V sync even in a player that ignores all MP4 edit lists (bound: one frame or the AAC priming, whichever is larger). So libx264 runs with `bframes=0`, copied video is re-encoded when its ignored-edit-list skew exceeds the bound, and `-avoid_negative_ts make_zero` is not used.
  - Any change to normalisation must keep the flash/beep sync tests passing, both honouring and ignoring edit lists, and must bump `NORMALISER_VERSION`.
- **Infrastructure:** no Celery, Redis, Docker Compose or Neo4j until the core pipeline is validated. Use SQLite jobs with one worker.
- Read `docs/reports/Embedding_Report.md` and `docs/reports/OCR_report.md` before changing anything they cover.
- **Whisper:** large-v3 (ADR-0039). The language is chosen per lecture from a two-tier list; Hindi -> `ur` is the only tested entry, every other language is untested, there is no default and no auto-detect (ADR-0040). Everything users read is English (ADR-0041). Stage design and failure codes: ADR-0042. A language moves to tested only through the WER gate in ADR-0040.
- **Still open:** LLM choice (qwen3.5 vs Gemma 4 E4B, M7), textbook (M0b), reranker, Test B and Test C.

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
- No hardcoded tunables in `backend/src/`. A new tunable goes into `config/default.yaml` with a comment (one line, with unit) and is read through the typed settings object (`insightex.core.config`). Entry points load settings once and pass them down.
- Every new or changed project decision gets an ADR in `docs/adr/` (template: `docs/adr/template.md`). A new decision gets a new ADR; a changed decision gets a new ADR that supersedes the old one, and the old ADR is never rewritten beyond its status line.
- Anything a browser plays needs a by-hand browser check before its module closes; ffmpeg-based measurements do not prove browser behaviour (ADR-0038).
- After any automated lint fix, run the full test suite (a ruff autofix once broke `sqlite3.Row` access).
- Git: do not add a Claude co-author trailer to commits.

## Where to look

| Need | File |
|---|---|
| Directory map | `README.md` |
| Models, storage map, VRAM budget | `docs/MODELS.md` |
| Build plan, exit criteria, pending decisions | `docs/BUILD_ORDER.md` |
| Per-feature spec (F1–F20) | `docs/features/README.md` |
| Why a decision was made | `docs/adr/`, `docs/reports/` |
| Decision log: one ADR per decision, with index and status (ADR-0001 to ADR-0042) | `docs/adr/README.md` |
| API contract (ingest link/upload, jobs, SSE, library) | `docs/contracts/api.md` |
| Draft JSON Schema: Ollama concept-extraction output (`concepts[]` with name, description, exam_relevant) | `docs/contracts/extraction.json` |
| Draft JSON Schema: ASR segment list (id, start, end, text, avg_logprob, no_speech_prob) | `docs/contracts/segments.json` |
| Current environment state, how to verify (`scripts/verify_env.sh`) | `docs/ENVIRONMENT.md` |
| Ollama call contract (ADR) and probe measurements | `docs/adr/0002-ollama-call-contract.md`, `docs/measurements/` |
| Setup and after-restart steps | `docs/runbooks/setup.md`, `docs/runbooks/after_restart_checklist.md` |
| Proposal, feature list (placeholder; documents not added yet) | `docs/proposal/README.md` |
| Reports: `Embedding_Report`, `OCR_report`, `vl_probe_REPORT`, `PRE_MIGRATION_AUDIT`, `MIGRATION_REPORT` | `docs/reports/` |
| Test lecture (mp4, WAVs, SRT/JSON, Roman-Urdu reference, queries) | `~/insightex-data/eval/day04_batch_vs_online/` |