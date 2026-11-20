# Insightex M7 handoff 5 (20 Nov 2026): M7 closed, before Session 3 (the production extraction stage)

For a fresh session. Read this first, then:
- `CLAUDE.md`;
- `docs/reports/M7_extraction_report.md` (approved 20 Nov 2026: results, configuration, 25 limitations);
- ADR-0048 (Amendments 1–11), ADR-0049 (Amendments 1–2), ADR-0050 to ADR-0053.

Trust the files over this summary when they differ. Handoff 4 covers the state before the held-out lecture.

## 1. Where things stand

- **M7 is closed** (exit met: precision/recall on 2 lectures, LLM choice decided). Day 4 concept F1 0.320 (gold v2.1); held-out `yt-5vqk6HnITko` concept P 0.136, R 0.412, F1 0.204 adjudicated (string rule 0.161), run once on 19 Nov 2026.
- **What exists:** the evaluation harness `insightex extract-eval run|measure` (`backend/src/insightex/extract/`, harness version 8), extraction schema v1 and its validator (`extraction.schema.json`, `extraction_schema.py`), the frozen prompts in `config/prompts/`, the arms in `config/m7_arms.yaml`, the labelling and scoring tool `tools/label_concepts/`.
- **What does not exist:** a production `extract` stage in the job pipeline, canonicalisation, the graph. Session 3 builds the stage; canonicalisation and the graph are M8.

## 2. The final configuration (frozen; the starting point for production)

| Setting | Value |
|---|---|
| Model | `gemma4:e4b`, digest `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`, Ollama 0.40.2 (app auto-update off; `docs/evidence/m7/scripts/check_ollama_frozen.py` before any measured run) |
| Input | the original-language transcript of each 30 s grid window (ADR-0045, ADR-0051) |
| Unit | one window per call (ADR-0052) |
| Context | none (ADR-0053) |
| Prompt | `config/prompts/m7_extraction_v2.txt`, sha256 `c7e061fce838d935c7335b01746fbec8c708f2d1f3845720c8e5728ac7154648`; system message sha256 `f2d8742f5155f1d1afef4ebc0324cfb0108a05de97185ff2167e4d30bac1a35f` |
| Call settings | `num_ctx` 8192; `num_predict` 1024 per window; temperature 0, seed 42, `think` false; `keep_alive` 0 (reload per call); `truncate` false; post-call overflow check; run-start truncation self-test; estimate gate as a warning only (Gemma scale 0.761); one retry in the same unit with the frozen `<<<RETRY>>>` template; dangling relations dropped and counted |
| Output | extraction schema v1: concepts (label + aliases), relations (`part_of`, `contrasts_with`, `example_of`, …), `important` + cue, `is_recap`; at most 10 concepts and 10 relations per window |
| Arm | `C4-window` (identical to `C1-gemma4-e4b`, `C2-original`, `C3-single`) |
| Cost | about 9 s per window on the RTX 3070, of which 6.3–7.1 s is the model reload; about 4.8 GB VRAM above baseline (Day 4 4,828 MiB, held-out 4,772 MiB) |

## 3. The held-out rule

**The held-out lecture (`yt-5vqk6HnITko`) has been used once and its output has been read** (`docs/evidence/m7/heldout/readthrough.md`). No Session 3 change (none of the decisions below, and nothing else: no stop list, prompt change, filter or post-processing) may be evaluated on it, or on Day 4 alone and reported as a held-out result. A change that needs a quality figure needs **new evidence on a fresh lecture** with its own gold, selected and labelled under ADR-0048's rules before any model output for it is seen. The M7 held-out figures stay those of the frozen configuration (report limitation 24).

Day 4 remains the dev lecture: it may be used to develop and debug, but it has been used for every M7 decision and is not independent evidence.

## 4. Open Session 3 decisions

Each is a separate decision, needs its own evidence, and gets its own ADR (a changed decision supersedes, never rewrites, the old ADR).

1. **Keep the model loaded between single-window calls.**
   - Why: about 70% of the per-window time is the reload under `keep_alive` 0 (report section 5; ADR-0052 found most of batching's speed-up came from fewer reloads).
   - Against: ADR-0049 chose reload per call because Gemma's output depended on session state; reload made repeats byte-identical.
   - Evidence needed: determinism (repeated runs with the model kept loaded, byte-identical or not, on the same windows) and, if outputs change, a quality check on a fresh lecture. Speed and VRAM measured with `--fresh`.
2. **Self-pointing relations** (ADR-0053). Drop a relation whose head equals its tail and count it, as dangling relations are dropped, instead of failing the window. This changes validity handling for every configuration; under it, C4's window 6 would not have failed on that rule (not re-run). Evidence: a rule change with tests; no quality claim without a fresh lecture.
3. **A stop list for generic labels and confusion-matrix-cell-like terms.**
   - Day 4 read-through: generic "model", the example's setting. Held-out read-through: "spam", "blunder", "model", example-table parts (feature, y, predicted, actual), and 33 of 103 concepts are individual confusion-matrix cells.
   - Open: a fixed list, a rule in the prompt (a new prompt version, which needs its own freeze), or post-processing; and whether finer terms like cells are wrong or only finer than the gold (report limitation 25).
   - The patterns came from reading held-out output, so **any filter derived from them must be evaluated on a fresh lecture only.**
4. **Canonical-name handling for M8.**
   - Seen: the speaker's surface forms as labels ("performance matrix", "imbalance data set"), abbreviations or unclear tokens as labels ("tp", "ff") and whole sentences as aliases (held-out window 10), and the parameter "beta" as its own concept.
   - Decide what the stage writes (raw model labels plus aliases, as v1 records) and what M8 owns (merging, textbook names, ADR-0019). The M8 exit is the duplicate-node rate on 2 lectures.
5. **Whether to keep relations and importance at all.**
   - **Relations** were never evaluated: neither gold has a relation (report limitation 7). The model produced 5 (Day 4) and 24 (held-out), all unmatched, and the read-throughs found reversed directions, category errors and invented `contrasts_with`. C4 was lost on a relation (head = tail).
   - **Importance** is barely evaluated (one gold important window in 60) and over-flagged (9 model windows against 1 on the held-out lecture, mostly on emphasis words; some cues copy the transcript against the guide).
   - `is_recap` was never true on the held-out lecture.
   - Options: drop them from the production schema, keep them stored but unused, or keep them with filters. Importance feeds F4 and `is_recap` F20, and relations feed the M8 graph, so dropping them changes those features' plans. Evidence for keeping them needs a fresh lecture whose gold has relations and important windows.

Also carried from handoff 4, each with its own evidence: context-aware extraction (not ruled out, needs new evidence, ADR-0053); batching for throughput only after decision 1 (ADR-0052); production writes v1 records and imports `insightex.extract.extraction_schema` (ADR-0048 Consequences); a stage design consistent with the GPU contract (its own subprocess under the GPU lease, model unloaded in `finally`).

## 5. Open items

- **The untracked void v1 sheet.** `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/adjudication_sheets/C1-20261018T180252Z.json` was never opened or used. It stays untracked and undeleted until Bilal decides.
- **yt-dlp test crash.** In one full `pytest` run (9 Nov 2026), `test_ytdlp_download.py::test_byte_cap_enforced_by_hook_without_content_length` crashed the interpreter ("no Python frame"). It passed alone and on clean HEAD. Cause not investigated.
- **Inter-annotator figure for Day 4 gold v2/v2.1** (ADR-0048 Amendment 5, decision 5). The only Day 4 figure (0.240) was measured on gold v1. The held-out ceiling (0.190) is the clean inter-annotator figure for the thesis; a Day 4 v2 figure would not be blind on Bilal's side.

## 6. Evidence and tags

| What | Where |
|---|---|
| Report | `docs/reports/M7_extraction_report.md` |
| Day 4 runs and comparisons | `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C1`–`C4`, `c1_gemma_readthrough.md` |
| Held-out records | `docs/evidence/m7/heldout/` (selection, ingest, labelling, agreement, read-through) |
| Held-out run, k check, scores | `docs/evidence/m7/yt-5vqk6HnITko/heldout/` |
| Gold, adjudications, sheets | `tools/label_concepts/labels/<lecture>/` |
| Tags | `m7-day4-gold-v2.1-frozen`, `m7-c4-adjudications-v2.1-frozen`, `m7-heldout-labels-frozen`, `m7-heldout-agreement`, `m7-heldout-gold-frozen`, `m7-heldout-adjudications-frozen` |
