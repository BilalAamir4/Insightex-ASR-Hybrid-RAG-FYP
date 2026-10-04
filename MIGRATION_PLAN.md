# MIGRATION_PLAN

Status: **approved for Phase 2 with the decisions below.** Where a decision conflicts with the original plan text further down, the decision wins. The original plan text is kept unedited as the Phase 0/1 record.

## Approved decisions (override the plan below)
1. Drop `INSIGHTEX_ROOT`; keep the `_INSIGHTEX_ENV_LOADED` guard; update `check_shell_env.sh` and `verify_env_fix.sh` echoes.
2. Load-time tools go to `tools/bench_models/loadtimes/` (new folder in the target structure).
3. `run_F7_check.py`: KEEP in `tools/audit_env/`.
4. `results/window_comparison.md`: read. It compares the 512-token and 1024-token runs side by side (table a has both; table b and the decision rule use the 1024 run). **Mixed -> ARCHIVE** in `docs/reports/embedding_bakeoff/` with a one-line note in the archive README.
5. `test_bakeoff.py` and `selftest/`: REMOVE (recoverable from tag `import-baseline`). CLAUDE.md "Embedding bake-off commands" is rewritten to say the bake-off is complete, results are archived, and old commands can be recovered from the tag.
6. `run_probe.ps1`: no hardcoded username. The data dir is derived with `wsl -d Ubuntu-24.04 -- wslpath -w "$INSIGHTEX_DATA/eval/frames/out"`; `-DataDir` overrides.
7. Remove the insightex line from `~/.bashrc`. Keep `~/.profile`, written as `[ -f "$HOME/insightex/env/insightex_env.sh" ] && . "$HOME/insightex/env/insightex_env.sh"`. Both files are backed up first. `scripts/run_in_env.sh` sources the env script itself.
8. UNSURE resolved: KEEP `verify_6a_whisper.py` (bench_models/asr), `verify_6b_bge.py` (bench_models/embedding), `verify_6c_ollama.py` (bench_models/llm), `test_ollama_chat.py` and `test_ollama_json.py` (probe_ollama). REMOVE `verify_6d_faiss_networkx.py` and all `smoke_*.py`.
9. `STRUCTURE_AUDIT.md` is archived as `docs/reports/PRE_MIGRATION_AUDIT.md`.
10. ADR 0001 only from Embedding_Report.md "Decisions made". `docs/contracts/segments.json` and `extraction.json` are drafts with a `$comment` naming the source (extraction: real schema in `ollama_contract.py`; segments: sample JSON). No other ADRs or contracts.

### Corrections
- A. Editable install NOT approved; `~/envs/insightex` is not modified. Import check uses `PYTHONPATH=backend/src`; pyproject sets pytest `pythonpath = ["backend/src"]`, `testpaths = ["backend/tests"]`.
- B. `models.yaml`: asr `peak_vram_mib: null`, only the verified 5,530 MiB (large-v3, 10-minute run) in notes; 5,895 and 4,532 not recorded. ocr_vlm name "PaddleOCR-VL (0.9B)", real folder name from `~/.paddlex/official_models`, "1.6" marked unverified. Reranker notes null. `${INSIGHTEX_MODEL_CACHE_MASTER}` used in storage_path where possible.
- C. Repo-local git config only (user.name "Bilal Aamir", email bilalaamirr@gmail.com). No remote, no push. Co-Authored-By trailer kept.
- D. Modes normalized (files 644, `*.sh` 755, dirs 755) before commits; `.gitattributes`: `*.sh text eol=lf`, `*.py text eol=lf`, `*.ps1 text eol=crlf`. No CRLF found in any imported `.sh/.py/.ps1`.
- E. Phase 3 may also run read-only, GPU-free kept scripts (confirmed by reading).
- F. User starts Ollama before check 7; wait for them.
- G. `scripts/verify_env.sh` only if it is a plain list of calls to existing check scripts.
- H. Runbooks only from CLAUDE.md and ENV_AUDIT_REPORT.md; unverified items marked. `docs/proposal/` empty + README.
- I. `requirements.lock.txt` via `cp`, sha256 `f120c37f6dbb07387711b5b065ce0106a320b63b16d9f60acc4f4d1a599daba4`, no trailing newline added.

---
# Insightex migration: Phase 0 findings and Phase 1 plan (for approval)

## Context
This is the Phase 0 (read-only inventory) result and the Phase 1 plan. After approval, the first action is to write this content to `~/insightex/MIGRATION_PLAN.md` with the Phase 1 "create only" rule, then stop. Phase 2 does not start until you approve the open questions (§G). Nothing under `/mnt/e/FYP` was modified. I wrote only two files, both in the scratchpad (`p0.sh`, `p1.sh`: read-only grep/syntax checks). `ast.parse` was used instead of `py_compile`, so no `__pycache__` was created on E:.

## A. Phase 0 findings

**Existence (0f, 0g)**
- `~/insightex` and `~/insightex-data` do not exist.
- Not on disk: `FYP_Proposal.MD`, `Insightex_Final_Features.md`, `Insightex_Build_Order.md`, `Final_Proposal.tex`, `tools/eval_wer/wer_eval.py`. So `docs/proposal/` is empty + README, and `tools/eval_wer/` is empty + README.
- No files outside the audit's description, with the exceptions in the discrepancy list below.

**Truncation (0b): none found**
- `bash -n` passes for `env/insightex_env.sh`, `~/.bashrc` and all 12 `tools/env_audit/*.sh`.
- `ast.parse` passes for every `.py` under `tools/` and `embedding/tools/`. The only messages are `SyntaxWarning: invalid escape sequence '\F'` in `run_T4_audit.py:2` and `run_T5_claims.py:2` (a Windows path in a docstring). That is a warning, not truncation, and the code is left unchanged.
- No zero-byte files. `ENV_AUDIT_REPORT.md` ends on a complete sentence. `requirements.lock.txt` ends on a complete line. Brace counts balance in `run_probe.ps1` (6/6), and `start_ollama.ps1` has no blocks.
- `requirements.lock.txt` SHA256: `f120c37f6dbb07387711b5b065ce0106a320b63b16d9f60acc4f4d1a599daba4`. It has 83 newline characters; the audit says 84 lines, so there is probably no trailing newline.

**Audit vs disk discrepancies**
1. The audit says `embedding/requirements.lock.txt` has 68 lines and the root file has 84. The root file has 83 newline characters (see above). I did not count the embedding one.
2. The audit lists `results/` files as `analysis.md, doc_updates.md, per_query_results.csv, run_config.json, summary.*, window_comparison.md, windows_W*.csv`. All are present. **`results/window_comparison.md` has mtime 2026-10-02 19:40, after the `results_seq1024` run (19:38).** It may be a current doc rather than an outdated one (see Q4).
3. `~/.paddlex` is 1,985 MB and `E:\FYP\cache\paddlex` is 302 MB. Reported, not resolved.
4. Ollama is **not running right now**: `curl localhost:11434/api/tags` returned empty. GPU idle is 1,704 MiB, higher than the 1,002–1,006 MiB baselines in the audit. Phase 3 check 7 needs Ollama started (`start_ollama.ps1`). I will ask first, per CLAUDE.md.
5. The audit says `eq1_res.json` has `input_path: /mnt/e/FYP/data/frames/eq1.png`. This is a path inside a result file (evidence), not a code path. It will not be rewritten (see §C).

**Shell startup (0e)**
- `~/.bashrc:118` is `source /mnt/e/FYP/env/insightex_env.sh`.
- `~/.profile:29` is `source /mnt/e/FYP/env/insightex_env.sh`.
- Neither file sets any other insightex variable. `~/.bash_profile` does not exist.
- `~/.bashrc` returns at line 6-9 for non-interactive shells, **before** line 118. So `bash -lc` (non-interactive login) sources the env script once, via `.profile`. An interactive login shell sources it twice: `.profile` runs, then `.bashrc` through Ubuntu's default `.profile`.
- The script has a guard (`_INSIGHTEX_ENV_LOADED`), so the second source returns early. The double source is therefore harmless but wasteful.

**Env variables**
- Set by `insightex_env.sh`: `_INSIGHTEX_ENV_LOADED`, `INSIGHTEX_ROOT=/mnt/e/FYP`, `HF_HOME`, `HF_HUB_OFFLINE=1`, `OLLAMA_BASE_URL`, `PIP_CACHE_DIR`, `TORCH_HOME`, `LD_LIBRARY_PATH` (`/usr/lib/wsl/lib` + `nvidia-*/lib` dirs, with its `${LD_LIBRARY_PATH:+...}` dedup).
- Set in `start_ollama.ps1`: `OLLAMA_MODELS=E:\FYP\LLMs`, `OLLAMA_HOST=127.0.0.1:11434`.
- Read or set by Python scripts: `HF_HOME`/`HF_HUB_OFFLINE` (set in `load_single_model.py`, `smoke_embedding.py`, `test_whisper.py`, `verify_6b_loadtimes.py`), `VIRTUAL_ENV` (read in `verify_6a_whisper.py`), the `os.environ.get` loop in `check_env_vars.py`. `INSIGHTEX_ROOT` is only echoed by `check_shell_env.sh` and `verify_env_fix.sh`; no code reads it.

**Import/tool checks (hard constraint 9)**
- No script under `tools/` imports from `backend/` (it does not exist yet). No tool script imports another.
- `embedding/.../test_bakeoff.py:4` does `from tools.eval_embeddings.embed_bakeoff import ...` (relative to `embedding/`). It is classified REMOVE, so this is moot. If it is kept (Q5), that import would break.

**Duplication (constraint 13, reported only)**
- The VRAM sampler appears in `process_a_whisper.py`, `ollama_contract.py`, `verify_6b_bge.py` and `run_F6_audit.py` (per the audit; I did not diff the blocks).
- Whisper test loads appear in `test_whisper.py`, `test_whisper_direct.py`, `verify_6a_whisper.py` and `whisper_anomaly_audit.py`. `/usr/lib/wsl/lib/nvidia-smi` is hardcoded in about 9 scripts.

## B. Mapping (every inventoried file once)
Actions: copy = carried unchanged except paths; archive = evidence copy; remove = not carried (recoverable from tag `import-baseline` and from E:). "Leave" = stays on E: only. The full per-file table, including every result file, is generated into `MIGRATION_PLAN.md`; groups below expand 1:1.

### B1. Root, docs, env, tools/vl_probe
| Source | Target | Action | Class | Reason |
|---|---|---|---|---|
| CLAUDE.md | CLAUDE.md | copy + path edits | KEEP | rules file |
| requirements.lock.txt | requirements.lock.txt | copy (byte-identical) | KEEP | lockfile |
| STRUCTURE_AUDIT.md | (none) | leave | n/a | description only (Q9) |
| docs/Embedding Report.md | docs/reports/Embedding_Report.md | rename | KEEP | decision record |
| docs/OCR_report.md | docs/reports/OCR_report.md | copy | KEEP | decision record |
| env/insightex_env.sh | env/insightex_env.sh | copy + edits | KEEP | canonical env |
| tools/env_audit/ENV_AUDIT_REPORT.md | docs/reports/ENV_AUDIT_REPORT.md | rewrite (step 8) | KEEP | superseded findings inside |
| tools/vl_probe/probe.py | tools/probe_paddleocr_vl/probe.py | copy + path fix | KEEP | 30-frame bake-off pending |
| tools/vl_probe/run_probe.ps1 | scripts/windows/run_probe.ps1 | copy + path fix | KEEP | Windows harness |
| tools/vl_probe/__pycache__/probe.cpython-312.pyc | – | remove | REMOVE | bytecode |

### B2. tools/env_audit (55 flat files)
| Files | Target | Class |
|---|---|---|
| process_a_whisper.py, whisper_anomaly_audit.py | tools/bench_models/asr/ | KEEP |
| ollama_contract.py, probe_ollama.py, probe_think.py, run_F2_repro.py | tools/probe_ollama/ | KEEP |
| check_av.py, check_env_vars.py, check_files_integrity.py, check_imports.py, check_login_env.sh, check_ollama_endpoint.py, check_packages.py, check_paths.sh, check_ps.sh, check_shell_env.sh, check_wsl_health.sh, verify_env_fix.sh, verify_6e_sequential.py | tools/audit_env/ | KEEP |
| run_in_env.sh | scripts/run_in_env.sh | KEEP |
| start_ollama.ps1 | scripts/windows/start_ollama.ps1 | KEEP |
| load_single_model.py, run_loadtimes_benchmark.py, verify_6b_loadtimes.py, compare_caches.py, loadtimes_results.json | tools/bench_models/ (subfolder pending, Q2) | KEEP |
| verify_6a_whisper.py | (hold) | UNSURE: has cold + 2 warm runs per model; could be the source of the never-shown warm numbers. The shown warm medians come from `whisper_anomaly_audit.py` (T3). |
| run_F7_check.py | recommend tools/audit_env/ | UNSURE: the rule says REMOVE (`run_F*`) but CLAUDE.md line 30 and ENV_AUDIT_REPORT §next-steps name it as the cache hash verifier (Q3) |
| verify_6b_bge.py, verify_6c_ollama.py, verify_6d_faiss_networkx.py | (hold) | UNSURE: not named by any rule; 6b/6c are likely sources of the bge 3,089 MiB and Ollama figures |
| smoke_embedding.py, smoke_faiss_networkx.py, smoke_ollama.py | (hold) | UNSURE: duplicated by verify_6b/6d/6c (subject match), but the rule only removes them once the verify script is kept. Recommend REMOVE if 6b/6c/6d are kept. |
| smoke_paddleocr.py | (hold) | UNSURE: no `verify_6*` twin for PaddleOCR, so the "duplicated by" rule does not apply |
| test_ollama_chat.py, test_ollama_json.py | (hold) | UNSURE: not named by any rule; recommend tools/probe_ollama/ |
| run_T0.py, run_T0_port.py, run_T1_cache_integrity.py, run_T4_audit.py, run_T5_claims.py | – | REMOVE (audit runners; T1 superseded by F7) |
| run_F1_audit.py, run_F3_audit.py, run_F3_segments.py, run_F4_audit.py, run_F5_audit.py, run_F6_audit.py | – | REMOVE (outputs kept as data) |
| run_T2_contract.sh, run_T2_process_a.sh, run_T3_anomaly.sh | – | REMOVE (`run_T*.sh`) |
| fail_mode_test.sh, fail_whisper_test.py, update_shell_env.py, print_bashrc.sh | – | REMOVE |
| test_whisper.py, test_whisper_direct.py | – | REMOVE (near-duplicate test loads) |
| results/followup/ (T0, T1, T2, T2_process_a, T3, T4, T5 .txt) | ~/insightex-data/logs/env_audit/followup/ | copy, KEEP (data) |
| results/followup2/ (F1–F7 .txt, F3_segments.json) | ~/insightex-data/logs/env_audit/followup2/ | copy, KEEP (data) |

### B3. data/
| Source | Target | Action |
|---|---|---|
| data/day04_batch_vs_online/raw/lecture_test.mp4 | ~/insightex-data/eval/day04_batch_vs_online/raw/ | copy + sha256 |
| eval/clip_30s.wav, lecture_first10min.wav, manual_roman.txt, whisper_urdu.srt, whisper_large_v3_first10min.json | ~/insightex-data/eval/day04_batch_vs_online/eval/ | copy + sha256 |
| embedding/tools/eval_embeddings/queries.csv | ~/insightex-data/eval/day04_batch_vs_online/eval/queries.csv (also archived) | copy |
| data/frames/eq1.png | ~/insightex-data/eval/frames/eq1.png | copy |
| data/frames/out/{eq1.md, eq1_layout_det_res.png, eq1_res.json, key_inventory.txt, vram_run1/2/a/b/c.csv} | ~/insightex-data/eval/frames/out/ | copy |
| data/frames/out/REPORT.md | docs/reports/vl_probe_REPORT.md | copy (misplaced) |
| embedding/data/.../whisper_urdu.srt | – | REMOVE (identical SHA256 c0355747…, confirmed against the eval copy) |

### B4. embedding/
| Files | Target | Class |
|---|---|---|
| results_seq1024/ (summary.csv/md, per_query_results.csv, run_config.json, windows_W30/W60/W90.csv) | docs/reports/embedding_bakeoff/results_seq1024/ | ARCHIVE |
| tools/eval_embeddings/queries.csv, results/doc_updates.md, embed_bakeoff.py | docs/reports/embedding_bakeoff/ (+ new README.md) | ARCHIVE |
| results/window_comparison.md | (hold) | UNSURE (Q4) |
| results/{analysis.md, per_query_results.csv, run_config.json, summary.csv, summary.md, windows_W30/60/90.csv} | – | REMOVE (512-token run) |
| test_bakeoff.py | – | REMOVE (but see Q5) |
| selftest/ (fake_queries.csv, fake_transcript.srt, output_dryrun/, output_offline/, output_real/: 2 inputs + 21 outputs) | – | REMOVE (see Q5) |
| requirements.lock.txt, .pytest_cache/ (4 files), __pycache__/ (2 .pyc) | – | REMOVE |
| .venv/ (7.2 GB, ~39k files) | – | REMOVE, never copied; original stays on E: |

## C. Hardcoded paths and replacements
| Where | Current | Replacement |
|---|---|---|
| env/insightex_env.sh (5 lines) | `/home/bilal_aamir/...` | `$HOME/...`; `INSIGHTEX_ROOT` see Q1 |
| scripts/run_in_env.sh | `/mnt/e/FYP/env/...`, `/home/bilal_aamir/envs/insightex/bin/activate` | `source "$(dirname "$0")/../env/insightex_env.sh"`, `source "$HOME/envs/insightex/bin/activate"` |
| process_a_whisper.py:16-18 | `/mnt/e/FYP/data/...` | `INSIGHTEX_DATA`-relative (`$INSIGHTEX_DATA/eval/day04_batch_vs_online/...`) via `os.environ["INSIGHTEX_DATA"]` (path-only change) |
| ollama_contract.py:23-24 | segments JSON, `results/followup/T2.txt` | `INSIGHTEX_DATA`-relative; output to `$INSIGHTEX_DATA/logs/env_audit/followup/T2.txt` |
| probe.py:61-62 | `/mnt/e/FYP/data/frames/{eq1.png,out}` | `$INSIGHTEX_DATA/eval/frames/...` |
| compare_caches.py:4-5 | master `/mnt/e/FYP/cache/...`, runtime `/home/bilal_aamir/...` | `$INSIGHTEX_MODEL_CACHE_MASTER/huggingface/hub`, `$HF_HOME/hub` |
| check_files_integrity.py, check_paths.sh, check_shell_env.sh, verify_env_fix.sh, run_F7_check.py, smoke_*.py, verify_6*.py, load_single_model.py, run_loadtimes_benchmark.py | `/mnt/e/FYP/...`, `/home/bilal_aamir/...` | derived from `INSIGHTEX_*`, `HOME`, `HF_HOME`. `check_files_integrity.py` and `check_paths.sh` check E: files by design; the new paths will point at the new repo for repo files and at `INSIGHTEX_MODEL_CACHE_MASTER` for caches. |
| `/usr/lib/wsl/lib/nvidia-smi`, `/usr/bin/ffmpeg` | system paths | **leave as is**: not under /mnt/e or /home; they are Linux system tools. Reported as a deliberate exception. |
| loadtimes_results.json, results_seq1024/run_config.json, results/followup*/*.txt, eq1_res.json | recorded paths | **not edited**: data/evidence. Excluded from the Phase 3 grep as "archived result files". The grep also excludes `docs/reports/` and `MIGRATION_PLAN.md`. |
| `docs/Embedding Report.md:94` | `...\FYP Testing\...` | left (evidence text, in docs/reports) |
| start_ollama.ps1 | `OLLAMA_MODELS = "E:\FYP\LLMs"` | **unchanged** (stays as is per config_rules) |
| run_probe.ps1 | `E:\FYP\data\frames\out\vram_run$RunLabel.csv`; `/mnt/e/FYP/tools/vl_probe/probe.py` | add `[string]$DataDir = "\\wsl$\Ubuntu-24.04\home\bilal_aamir\insightex-data\eval\frames\out"` as default **or** write the CSV to a temp path and copy; probe path via `wsl -d Ubuntu-24.04 -- bash -lc 'source ~/envs/paddleocr-vl/bin/activate && python "$INSIGHTEX_HOME/tools/probe_paddleocr_vl/probe.py"'`. I recommend a `-DataDir` parameter whose default is the `\\wsl$` path, and referring to `$INSIGHTEX_HOME` inside WSL (set by `.profile`, which `bash -lc` reads). The `\\wsl$` path embeds the username; Q6. |

## D. Env changes
| Var | Current | Proposed |
|---|---|---|
| HF_HOME | /home/bilal_aamir/cache/huggingface | $HOME/cache/huggingface |
| PIP_CACHE_DIR | /home/bilal_aamir/cache/pip | $HOME/cache/pip |
| TORCH_HOME | /home/bilal_aamir/cache/torch | $HOME/cache/torch |
| NVIDIA_SITE (internal) | /home/bilal_aamir/envs/insightex/... | $HOME/envs/insightex/... (dedup logic unchanged) |
| HF_HUB_OFFLINE, OLLAMA_BASE_URL | 1, http://localhost:11434 | unchanged |
| INSIGHTEX_HOME / INSIGHTEX_DATA / INSIGHTEX_MODEL_CACHE_MASTER | unset | $HOME/insightex / $HOME/insightex-data / /mnt/e/FYP/cache |
| INSIGHTEX_ROOT (=/mnt/e/FYP) and `_INSIGHTEX_ENV_LOADED` guard | present | **conflict with "add exactly three"**; see Q1 |
| OLLAMA_MODELS (Windows), OLLAMA_HOST (ps1) | | unchanged |

**Startup files** (back up each as `<file>.bak-YYYYmmdd-HHMMSS` next to the original; edits only after approval):
- `~/.profile:29` before: `source /mnt/e/FYP/env/insightex_env.sh`; after: `source "$HOME/insightex/env/insightex_env.sh"`.
- `~/.bashrc:118` before: `source /mnt/e/FYP/env/insightex_env.sh`; after: line removed (Q7).
- This leaves one source per login shell. `bash -lc` still gets the env (it reads only `.profile`). Removing from `.profile` instead would make Phase 3 check 1 fail, because `.bashrc` returns early in non-interactive shells.
- Interactive non-login shells inherit exported variables from the login parent. They would lack them only if started cold (no login parent).

## E. Draft config
`config/default.yaml`:
```yaml
window_seconds: 30
visual:
  enabled: false
paths:
  home: ${INSIGHTEX_HOME}
  data: ${INSIGHTEX_DATA}
  model_cache_master: ${INSIGHTEX_MODEL_CACHE_MASTER}
  hf_home: ${HF_HOME}
endpoints:
  ollama_base_url: ${OLLAMA_BASE_URL}
# ingest:
#   url:
#     # values not yet decided
```
No `num_ctx`/`think`/`format`/`keep_alive`. `config/local.yaml`: empty, with a one-line comment, gitignored.

`config/models.yaml` (keys exactly: key, type, name, runtime, device, precision, used_by, storage_path, runtime_path, venv, peak_vram_mib, status, decision_ref, notes; null where unknown):
```yaml
- key: asr
  type: asr
  name: faster-whisper            # checkpoint NOT chosen
  runtime: CTranslate2
  device: cuda
  precision: float16
  used_by: [backend/src/insightex/asr]
  storage_path: /mnt/e/FYP/cache/huggingface   # master
  runtime_path: ~/cache/huggingface
  venv: ~/envs/insightex
  peak_vram_mib: null             # see notes
  status: pending
  decision_ref: null
  notes: >
    Candidates cached: Systran/faster-whisper-medium, Systran/faster-whisper-large-v3. Waits on WER evaluation.
    large-v3 peak 5,530 MiB (10-min audit, ENV_AUDIT_REPORT, T2_process_a.txt line 33).
    The prompt's 5,895 MiB (large-v3, 30 s) and 4,532 MiB (medium, 30 s) were NOT found as VRAM figures on disk: 5,895 appears only as a (wrongly doubled) cache SIZE in F7.txt/T1.txt. Unverified, not recorded.
- key: llm
  type: llm
  name: qwen3.5:latest            # 9.7B Q4_K_M, id 6488c96fa5fa
  runtime: ollama
  device: cuda
  precision: Q4_K_M
  used_by: [backend/src/insightex/llm, backend/src/insightex/extract]
  storage_path: E:\FYP\LLMs       # Windows OLLAMA_MODELS
  runtime_path: null
  venv: null
  peak_vram_mib: 7566
  status: pending
  decision_ref: null
  notes: "Fallback candidate Gemma 4 E4B. Peak at num_ctx 8192 per audit (626 MiB headroom). Unload with keep_alive 0."
- key: embedding
  type: embedding
  name: BAAI/bge-m3
  runtime: sentence-transformers
  device: cuda
  precision: null
  used_by: [backend/src/insightex/index]
  storage_path: /mnt/e/FYP/cache/huggingface
  runtime_path: ~/cache/huggingface
  venv: ~/envs/insightex
  peak_vram_mib: 3089
  status: decided
  decision_ref: docs/reports/Embedding_Report.md; docs/adr/0001-bge-m3.md
  notes: "1024-d, 30 s windows. Peak is standalone, measured 2 Oct 2026, not re-run. Rejected candidate (tied, not chosen): Qwen/Qwen3-Embedding-0.6B."
- key: reranker
  type: reranker
  name: null
  runtime: null
  device: null
  precision: null
  used_by: [backend/src/insightex/retrieval]
  storage_path: null
  runtime_path: null
  venv: null
  peak_vram_mib: null
  status: undecided
  decision_ref: null
  notes: "Should match the embedding family."
- key: ocr_vlm
  type: ocr_vlm
  name: PaddleOCR-VL 1.6 (0.9B)
  runtime: paddle
  device: cuda
  precision: null
  used_by: [workers/ocr, backend/src/insightex/visual]
  storage_path: ~/.paddlex
  runtime_path: ~/.paddlex
  venv: ~/envs/paddleocr-vl
  peak_vram_mib: null
  status: optional
  decision_ref: docs/reports/OCR_report.md
  notes: "max_memory_allocated ~3,097 MiB; nvidia-smi peak ~7,950 MiB (allocator reserve). Adoption gated on a 30-frame bake-off. Cache sizes differ: ~/.paddlex 1,985 MB vs E:\\FYP\\cache\\paddlex 302 MB (unresolved)."
```
Note: "PaddleOCR-VL 1.6" version string is from your prompt. The disk shows `paddleocr 3.7.0`/`paddlepaddle-gpu 3.2.1`. I could not find "1.6" in the files I read, so it is marked unverified in the notes.

## F. CLAUDE.md edits (paths only, plus the new section)
- `/mnt/e/FYP/tools/env_audit/run_in_env.sh` becomes `scripts/run_in_env.sh` (called from `~/insightex`).
- `/mnt/e/FYP` (shell root) becomes `~/insightex`; layout bullets for `docs/`, `tools/env_audit/`, `embedding/...`, `tools/vl_probe/`, `data/...` are repointed to `docs/reports/`, `tools/audit_env/` + `tools/bench_models/`, `docs/reports/embedding_bakeoff/`, `tools/probe_paddleocr_vl/`, `~/insightex-data/eval/`.
- `Embedding Report.md` becomes `Embedding_Report.md`; `run_F7_check.py` and `start_ollama.ps1` paths updated.
- "It is not a git repository" becomes git repo on `main` (needed for accuracy; facts only).
- The "Embedding bake-off commands" section: see Q5 (test_bakeoff/selftest are REMOVE). I propose keeping the section but noting the commands are reference-only in the archive.
- New section "Repository layout" pointing to README.md and docs/MODELS.md. No rule text altered.

## G. Questions (blocking Phase 2)
1. `INSIGHTEX_ROOT=/mnt/e/FYP` and the `_INSIGHTEX_ENV_LOADED` guard exist today. No code reads `INSIGHTEX_ROOT`. Keep both (guard is needed for the dedup), drop `INSIGHTEX_ROOT`, or repoint it to `$INSIGHTEX_HOME`? Recommend: keep the guard, drop `INSIGHTEX_ROOT` (and update the two echo scripts).
2. Where do the multi-model load-time tools go (`load_single_model.py`, `run_loadtimes_benchmark.py`, `verify_6b_loadtimes.py`, `compare_caches.py`, `loadtimes_results.json`)? They touch whisper and bge, so they don't fit `asr|embedding|llm`. Recommend `tools/bench_models/loadtimes/` (adds one folder to the target structure), or choose.
3. `run_F7_check.py`: CLAUDE.md names it as the cache verifier. Keep it in `tools/audit_env/` (recommended)?
4. `results/window_comparison.md` (mtime after the seq1024 run): archive or remove? I have not read its contents; I will read it before you decide if you want.
5. Removing `test_bakeoff.py` and `selftest/` contradicts CLAUDE.md's "verify on the synthetic selftest fixture" and bake-off commands. Confirm REMOVE, or archive them with `embed_bakeoff.py` so the dry-run stays reproducible (recommended; small).
6. `run_probe.ps1` default data path through `\\wsl$\Ubuntu-24.04\home\bilal_aamir\...` hardcodes the username on the Windows side. Accept?
7. Remove the line from `.bashrc` and keep `.profile` (recommended), or the reverse?
8. UNSURE items in B2 (verify_6a/6b/6c/6d, smoke_*, test_ollama_*): decide per row; my recommendations are in the table.
9. `STRUCTURE_AUDIT.md`: leave on E: only (current plan), or add to `docs/reports/`?
10. `docs/adr/0001-bge-m3.md` and `docs/contracts/{segments,extraction}.json` are new authored files. I will derive the ADR only from `Embedding_Report.md` §7 "Decisions made", and seed the contracts from the audit §5.2 samples (segments is an example not a schema; I'll produce a minimal JSON Schema from the sample and mark it draft). OK?

## H. Conflicts between the prompt and the disk
- CLAUDE.md "Ask before ... stopping Ollama" vs Phase 3 needing Ollama up. Following the prompt for actions; I'll ask before starting/stopping it.
- CLAUDE.md says "Never run two CUDA stages" and "free VRAM first (`ollama stop`)": Phase 3 check 9 is a CPU-import check (`import torch` etc.); baseline today is 1,704 MiB, so I'll compare before/after, not to the audit's 1,002 MiB.
- Whisper VRAM figures (5,895/4,532) not found on disk (see §E).
- "PaddleOCR-VL 1.6": not found on disk; unverified.
- Prompt says the VRAM sampler is in 4 scripts and Whisper loads in 4: consistent with the audit; I did not independently diff them.
- `embedding/requirements.lock.txt` copy forbidden (matches the plan; REMOVE).

## I. Editable install
`pip install -e . --no-deps` is needed only for `python -c "import insightex"` (Phase 3 check 3), because the package lives at `backend/src/insightex`. It changes `~/envs/insightex` (adds an `.egg-link`/`.pth` entry only, no dependency changes). I ask for approval for this one install. Without it, check 3 can run via `PYTHONPATH=backend/src` without touching the venv (alternative).

## Phase 2–4 execution notes (unchanged from your prompt)
- Order: baseline import (verbatim copy of all non-data text/code/docs into `_legacy_import/`, sha256-verified, tag `import-baseline`), skeleton, git mv, path edits, config/docs, env + shell files (with backups), CLAUDE.md, ENV_AUDIT_REPORT rewrite, archive + delete `_legacy_import/`. One commit per step: `restructure: <step>`; attribution trailer on each: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- `MIGRATION_PLAN.md` itself will be committed after the baseline tag (so the baseline contains only the verbatim import), as `restructure: migration plan`.
- Verification (Phase 3): the 10 listed checks with real outputs; GPU-free `run_in_env.sh` import check only.
- Never run the env_audit scripts outside Phase 3's named ones; no downloads, no pip changes besides the approved editable install.
