# Environment (current state)

Last verified: 2026-10-10, after M2 (lockfile gained ruff). `bash scripts/verify_env.sh` passed 12 of 12 from a fresh login shell (report `20261010T054412.json`). Earlier full-restart verification: 2026-10-07, boot 23:30:30. This replaces `docs/reports/ENV_AUDIT_REPORT.md` (still in git history). Labels: **MEASURED** = measured on the date shown; **CARRIED OVER** = measured earlier (2 to 4 Oct 2026) and not re-run.

## 1. Machine / OS

- Windows 11 Pro host, about 32 GB RAM (WSL sees about 15 GB), Intel Core i7 (20 threads, carried over), NVIDIA GeForce RTX 3070 (8,192 MiB), driver 616.64.
- WSL2 `Ubuntu-24.04` (24.04.5 LTS), kernel `6.18.40.1-microsoft-standard-WSL2`, mirrored networking (section 8).
- Run everything from a WSL shell. Do not nest commands through `wsl -- bash -lc "..."` from PowerShell; quoting breaks `$` and `&&`.

## 2. Storage layout

| Location | What | Notes |
|---|---|---|
| `E:\FYP` (`/mnt/e/FYP`) | Heavy storage and backup | `cache\` (master model cache), `LLMs\` (Ollama models), `wsl\` (the ext4 vhdx), `docker\`, `start_ollama.ps1`. Do not search, modify or delete `cache`, `LLMs`, `wsl`, `docker`. Never point runtime caches here (DrvFS loads are 3.5x to 7.4x slower; carried over). |
| `~/insightex` | Code (git repo, remote `Insightex-ASR-Hybrid-RAG-FYP`, tag `import-baseline`) | On the ext4 vhdx stored under `E:\FYP\wsl`. |
| `~/insightex-data` | Runtime data (`workspaces/`, `staging/`, `insightex.db`, `run/`, `eval/`, `logs/`, `env_reports/`; the old `lectures/` is no longer read) | `INSIGHTEX_DATA`. `staging/` holds uploads and copied files before ingest; it should be empty when idle, and the worker deletes staging files older than 24 h at start. |
| `~/cache/huggingface` | Runtime HF cache (ext4) | `HF_HOME`. Holds bge-m3, faster-whisper medium and large-v3. Master copy on `E:\FYP\cache`. |
| `~/envs/insightex`, `~/envs/paddleocr-vl` | Python venvs | PaddleOCR has its own venv. |

Nothing project-related should grow on C:.

## 3. Env script (`env/insightex_env.sh`)

Sourced once from `~/.profile`; `scripts/run_in_env.sh` sources it too and then activates the venv. It sets `INSIGHTEX_HOME`, `INSIGHTEX_DATA`, `INSIGHTEX_MODEL_CACHE_MASTER`, `HF_HOME`, `HF_HUB_OFFLINE=1`, `OLLAMA_BASE_URL=http://localhost:11434`, `PIP_CACHE_DIR`, `TORCH_HOME` and `LD_LIBRARY_PATH` (`/usr/lib/wsl/lib` plus the 15 `nvidia/*/lib` directories of the venv, 16 entries when started empty).

The venv `activate` script (`~/envs/insightex/bin/activate`, last line) sources this repo copy, guarded by an `if [ -f ... ]` block; `E:\FYP\env` is backup only and is not sourced by anything.

- **`LD_LIBRARY_PATH` has no empty entries** (fixed 2026-10-07). An empty entry means the current directory is searched for libraries. The script now joins entries without a trailing colon and handles an empty or preset prior value. `tools/verify_env.py` checks for empty entries and duplicates.
- **Once-per-shell guard** (`_INSIGHTEX_ENV_LOADED`): the script returns immediately if the variable is already exported, so it never duplicates entries. **Stale-session caveat:** a session that was started before the script was changed (an IDE terminal or agent session left open) keeps its old exported `LD_LIBRARY_PATH` and the guard stops the fix from being applied. After editing the script, open a new WSL session (or use `env -i HOME=$HOME PATH=/usr/bin:/bin bash -lc '...'` to test).
- Without the wrapper, faster-whisper fails at **inference** time with `libcublas.so.12 is not found`, not at import.

## 4. Venv and lockfile

- `~/envs/insightex`: Python 3.12; torch 2.11.0+cu128, faster-whisper 1.2.1, ctranslate2 4.8.2, sentence-transformers 6.1.0, transformers 5.18.0, faiss-cpu 1.15.1, networkx 3.6.1, pydantic 2.13.5, httpx 0.28.1, uroman 1.3.1.1 (romanisation for the WER gate in `tools/eval_wer`; locked 10 Oct 2026).
- `requirements.lock.txt` (repo root, 97 packages, counted 2026-10-10) is the pin set. It **intentionally omits the editable `insightex` install** (this repo), and `pip freeze` itself omits `pip`, `setuptools` and `wheel`. `tools/verify_env.py` ignores exactly those four and fails on any other mismatch.
- Dev tools: `ruff==0.16.10`, pinned in the `dev` extra of `pyproject.toml` and in the lockfile (added 9 Oct 2026). Install with `pip install -e '.[dev]'`.
- No installs, upgrades or removals without asking. `FlagEmbedding` is not installed (and not locked); `tools/bench_models/loadtimes/verify_6b_loadtimes.py` needs it for its bge-m3 step and fails there.
- ffmpeg/ffprobe: Ubuntu native 6.1.1. Normalisation (ADR-0036 to ADR-0038) requires the `libx264` and `aac` encoders. The media test fixtures also use `libx265`, `libvpx-vp9`, `libaom-av1`, `libsvtav1`, `mpeg2video`, `wmv2`, `libopus`, `libmp3lame` and `mjpeg`. All were present when checked on 9 Oct 2026 (`ffmpeg -hide_banner -encoders`). Normalisation is CPU-only and takes no GPU lease.

## 5. Ollama

- Runs on **Windows**, loopback only: `127.0.0.1:11434` (MEASURED 2026-10-07: the Windows `ollama.exe` process is the only listener; WSL reaches it as `localhost` through mirrored networking). Version **0.35.1** per `/api/version` (read after the restart on 2026-10-07; the old audit recorded 0.33.3). **Windows Ollama auto-updates**, so the version can change without notice. Rule: **re-run `tools/ollama_contract_probe.py` after any Ollama update** and compare with `docs/measurements/`. See the 0.35.1 confirmation line in section 7.
- Models live in `E:\FYP\LLMs`. `/api/tags` lists exactly `qwen3.5:latest` (9.7B, Q4_K_M, id `6488c96fa5fa`).
- Start script: `scripts/windows/start_ollama.ps1` in the repo is the **source of truth**. It sets `OLLAMA_MODELS=E:\FYP\LLMs` and `OLLAMA_HOST=127.0.0.1:11434` for its own process, then runs `ollama serve`. `E:\FYP\start_ollama.ps1` is a **deployed copy** (it is what Task Scheduler runs) and **must be re-copied by hand after any change to the repo copy**. Check with `diff <(tr -d '\r' < scripts/windows/start_ollama.ps1) <(tr -d '\r' < /mnt/e/FYP/start_ollama.ps1)` (no output = same content). The two files are not byte-identical, only identical after stripping CR: the repo checkout has CRLF line endings (`.gitattributes`: `*.ps1 eol=crlf`; the committed blob is LF) and the `E:\FYP` copy has LF only (191 vs 195 bytes, checked 2026-10-07). PowerShell accepts both.
- **Autostart:** Task Scheduler task `Insightex Ollama` runs `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "E:\FYP\start_ollama.ps1"`. MEASURED after the restart: Windows booted 23:30:30, `ollama.exe` started 23:30:56, task state Running, `/api/tags` answered with no manual step.
- **Desktop-app autostart is disabled** (stated by the project owner; setting not inspected here). Only one `ollama` process was running after boot and no tray-app process.
- Never set `OLLAMA_HOST=0.0.0.0`. Do not change Ollama or Windows settings from WSL work; changes there are made by hand.
- Before any GPU stage run **outside the worker** (benchmarks, `tools/`): `ollama ps`, and unload (`keep_alive: 0`) if a model is resident. Ask before stopping Ollama. GPU stages **run by the worker** (such as `asr`) get the Ollama model unloaded by the GPU lease on acquire (ADR-0033), so no manual step applies there. `tools/m4_verify` aborts if a model is loaded and prints the `ollama stop <model>` to run. Not yet exercised end to end in M4: Ollama was not running during the M4 verification runs.

## 6. Call contract

Summary: `chat_json(messages, schema, num_ctx, num_predict=1024, ...)` in `backend/src/insightex/llm/ollama_client.py`. Exact model name checked first, `think: false`, JSON Schema `format` from a pydantic model, `num_ctx` required (project default 8192), `num_predict` explicit, budget rule estimated prompt + `num_predict` <= `num_ctx`, `done_reason: length` raises `OutputTruncated` and is never parsed, `unload()` with `keep_alive: 0` plus polling. Full table, numbers and alternatives: **`docs/adr/0002-ollama-call-contract.md`**.

## 7. Measured numbers

| Item | Value | Date, source |
|---|---|---|
| Idle VRAM (Windows desktop only, no model) | 600 to 1,273 MiB (1,273 right after boot, 600 later) | 2026-10-07, `nvidia-smi` |
| qwen3.5 at `num_ctx` 8192, 6.9k-token prompt | peak 7,374 to 7,682 MiB, model share 6,495 to 6,601 MiB, **510 to 818 MiB free** (depends on the desktop baseline, 852 to 1,081 MiB), 100% GPU, 52.1 to 63.7 tok/s | 2026-10-07, `docs/measurements/2026-10-07_ollama_contract.md` |
| qwen3.5 at `num_ctx` 16384, 13.7k-token prompt | 16%/84% CPU/GPU, 44.4 tok/s (not usable at 100% GPU) | same file; one run, old 600-token cap |
| Whisper medium / large-v3 load, cold then warm | 4.35 / 0.78 s and 7.92 / 1.78 s | 2026-10-07, `docs/measurements/2026-10-07_loadtimes.md` |
| bge-m3 load (sentence-transformers), cold then warm | 6.48 / 1.59 s | same file |
| Whisper warm speed on Day 4 first 10 min (speed only) | medium 21.4x real time (RTF 0.0466), large-v3 8.4x (RTF 0.1197) | same file; WER is M4 |
| ~~Whisper large-v3 peak VRAM, 10 min~~ | ~~5,530 MiB~~ **superseded** by the production rows below (different method; not re-run) | 3 Oct 2026, CARRIED OVER |
| **Production large-v3 ASR on Day 4** (the `asr` stage, language `hindi` -> `ur`, float16, 688.03 s of audio, 351 segments, 0 temperature-fallback segments) | wall time 78.025 s (transcription only, model load excluded), **RTF 0.1134**, peak VRAM **4,523 MiB above the pre-stage baseline** (1,164 MiB); VRAM back within 8 MiB of baseline after the stage; whole job (normalise + ASR) 86.6 s | **MEASURED** 2026-10-10, `docs/evidence/m4/m4_verify_20261010T094558Z.json` (checks 2 and 7); a first run the same day gave RTF 0.1132, peak 4,504 MiB (`…T094021Z.json`) |
| bge-m3 peak VRAM | 3,089 MiB | 2 Oct 2026, CARRIED OVER (the bake-off measured 1,141.7 MB, see `Embedding_Report.md`) |
| **Confirmed on Ollama 0.35.1** (version read from `/api/version` by the probe) | the 8192 / 6,905-token case was re-run after the restart: 100% GPU, `done_reason` `stop`, valid JSON, 786 output tokens, peak 7,682 MiB, 510 MiB free, 52.1 tok/s, load 29.7 s (baseline 1,081 MiB). The earlier long-prompt runs were made before the restart, and the Ollama version they ran on was not recorded. | 2026-10-07 23:44, same measurements file |
| `tools/verify_env.py` after full restart | 12 of 12 passed | 2026-10-07, report `$INSIGHTEX_DATA/env_reports/20261007T233720.json` |
| `tools/verify_env.py` after M2 | 12 of 12 passed; idle baseline 1,382 MiB; `chat_json` 100% GPU at 65.4 tok/s (33-token prompt only) | 2026-10-10, report `$INSIGHTEX_DATA/env_reports/20261010T054412.json` |
| Idle VRAM observed 2026-10-10 | 1,382 to 1,601 MiB, above the 600 to 1,273 MiB recorded on 2026-10-07 | 2026-10-10, `verify_env.py` runs; the long-prompt headroom was **not re-measured** at this baseline |

GPU contract (hard): never two CUDA stages at once; each stage is its own process and exits fully before the next starts. At query time the GPU belongs to Ollama; bge-m3 query encoding and the reranker run on CPU inside the API process (planned, M5).

## 8. .wslconfig

`C:\Users\<user>\.wslconfig` contains `[wsl2]` and `networkingMode=mirrored`. A byte-identical reference copy is `env/wslconfig.reference` (BOM and CRLF kept); date copied and the "no original backup found" note are in `env/README.md`. Mirrored networking is why WSL reaches Windows Ollama at `localhost:11434`.

## 9. Do NOT do

- **Do not set `OLLAMA_HOST=0.0.0.0`.** Ollama stays loopback-only.
- **Do not symlink WSL caches** (`~/.cache/pip`, `~/.paddlex`, `~/.cache/paddle`, HF/torch caches) **into `/mnt/e` or `/mnt/c`.** DrvFS loads were measured 3.5x to 7.4x slower. `tools/verify_env.py` fails if a cache resolves into `/mnt`.
- **Do not trust the old audit scripts for `LD_LIBRARY_PATH`.** `tools/audit_env/check_login_env.sh` and similar counted entries with `grep -v '^$'`, which hid the empty entry (trailing colon) that existed until 2026-10-07. Use `tools/verify_env.py`.
- Do not run `tools/bench_models/loadtimes/verify_6b_loadtimes.py` casually: it calls `sudo tee /proc/sys/vm/drop_caches`, its bge-m3 step needs a package that is not installed, and it reads `E:\FYP\cache` when that path exists.
- Do not run two GPU stages together, and do not leave a model loaded in Ollama before starting one.

## 10. Known risks

- **VRAM headroom is 510 to 818 MiB** at `num_ctx` 8192 with a 7k-token prompt (peak 7.4 to 7.7 GB of 8.19 GB), depending on how much the Windows desktop holds (baseline 852 to 1,081 MiB across runs).
- **Windows apps eating VRAM.** GPU-heavy Windows apps took about 2.3 GB at one point; with that load the model does not fit at 100% GPU. Close them during work and check the idle baseline.
- **Urdu token cost.** Urdu script costs far more tokens per character than English; the budget rule's 1.5 chars/token for Arabic script is a guess. No Urdu-script prompt has been run through the probe, so context headroom for real Urdu lectures is unmeasured.
- **Ollama updates itself** (Windows auto-update). Version moved from 0.33.3 to 0.35.1 between audits; a new version can change memory use or the CPU/GPU split. Re-run `tools/ollama_contract_probe.py` after any Ollama update.
- Extraction quality is not evaluated (see M7 open items in the ADR).
- **Ollama state is not guaranteed at login.** On 2026-10-10 Ollama was not running, and once started, `qwen3.5:latest` was found loaded at `context_length` 4096 (Ollama's default, so not loaded by Insightex, which always sets `num_ctx`). Cause not identified. Before GPU work, check `/api/ps` and unload with `curl -s localhost:11434/api/generate -d '{"model":"qwen3.5:latest","keep_alive":0}'`. If the model reappears unprompted, find the Windows client loading it.

## 11. How to verify

```bash
bash ~/insightex/scripts/verify_env.sh     # wrapper for tools/verify_env.py
```

It prints a PASS/FAIL/SKIP table and writes `$INSIGHTEX_DATA/env_reports/<timestamp>.json`. Exit code 0 only if everything passes. It checks: env vars and caches, lockfile match, ffmpeg/ffprobe, FAISS, NetworkX, Ollama `/api/tags`, GPU idle baseline, and, each in its own process, torch CUDA, faster-whisper medium on 10 s of Day 4 audio, bge-m3 offline (1024-d), `chat_json` (schema-valid, truncation and budget paths, 100% GPU), and VRAM back within 200 MiB of baseline after unload. Ollama must be running first (Task Scheduler does this at logon). Run it from a new WSL session so the stale-session caveat in section 3 does not apply.

## 12. Running the app

```bash
bash ~/insightex/scripts/dev_run.sh          # worker in the background, API + UI in the foreground (http://127.0.0.1:8000)
```

- The worker (`insightex worker`) is a **separate process** from the API. The API only enqueues jobs and reads their state; without a worker, a submitted link or upload stays "Waiting for the worker". `dev_run.sh` starts one unless another already holds `<run_dir>/worker.lock`, and stops the one it started when you press Ctrl-C. Worker log: `$INSIGHTEX_DATA/logs/worker.log`.
- **Restart after code changes.** A running server and worker keep the code they started with. After pulling or merging, stop `dev_run.sh` (Ctrl-C) and start it again.
- `insightex gpu status [--json]` shows whether the GPU lease is free or busy and who holds it (also `run_dir`, `workspaces_dir` and the Ollama settings).
- Cache: `insightex cache list | delete ID | pin ID | unpin ID | gc` (the library's Delete button is `cache delete`). The cache is capped by `cache.max_bytes`; least recently used unpinned workspaces are evicted after each successful job.
- Pin evaluation lectures so eviction never removes them: `insightex cache pin <workspace id>`. The id is `yt-<video id>` for YouTube links and `sha256-<32 hex>` for uploads and other files; `insightex cache list` shows it.
- Jobs: `insightex jobs list | show ID | cancel ID | retry ID`.
- Ingest from the shell: `insightex ingest URL --confirm-rights` for a link, `insightex ingest-file PATH --confirm-rights [--wait]` for a local file (exit 0 ok or deduplicated, 2 rejected, 1 internal error). The original file is never moved or modified. In the browser, use the upload form; the file picker shows video files only (switch the dialog to "All Files" to pick anything else).
- Uploading the same bytes again returns the existing lecture instead of reprocessing. After a `NORMALISER_VERSION` bump it re-normalises in place.
- Lectures ingested before M1 session 3 live in `~/insightex-data/lectures/`. They are not migrated and not read; add them again by link or upload.