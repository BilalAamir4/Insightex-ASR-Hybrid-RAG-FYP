# Insightex: Embedding Work — Decisions, Plan, and Status

Last updated: 3 October 2026

This file records everything decided so far about choosing the embedding model for Insightex, how the work was done, what the results were, what is still open, and what comes next.

---

## 1. The goal

Choose an **evidence-based, defensible embedding model and chunk size** for the retrieval layer (the FAISS side of the hybrid KG + vector design), using **your own code-switched lecture data** instead of leaderboards.

The finished deliverable has four parts:

1. A results table from your own lecture data.
2. A chosen model (and, later, a matching reranker).
3. A chunking decision (window size) ready for the Milestone 4 FAISS build.
4. A concrete example of evaluation-driven design for the defense.

---

## 2. Why this decision exists

Insightex embeds three kinds of text:

| Text | Language | Notes |
|---|---|---|
| Lecture transcript segments | Urdu script (occasionally Devanagari) with English technical terms mixed in | Noisy, code-switched |
| Textbook page chunks | Clean English | Needed for timestamp-to-page fusion (Feature 1) |
| Queries and concept labels | English | |

The model must therefore handle **cross-lingual matching** (English query to Urdu-script transcript) and **noisy-vs-clean matching** (transcript to textbook page).

---

## 3. Fixed project decisions this work builds on

- **Scope:** ASR is the committed pipeline. The visual/OCR pipeline is optional, behind a config flag.
- **Hardware:** RTX 3070, 8 GB VRAM. Models load, process and unload per stage; they never coexist in GPU memory.
- **Retrieval design:** hybrid knowledge graph (NetworkX) + FAISS vector index, with a router. The embedding model serves the FAISS side.
- **Feature 1 exit criterion (later test):** book page within ±2 pages across at least 20 test queries.

---

## 4. Candidates and the decision method

| | BGE-M3 | Qwen3-Embedding-0.6B |
|---|---|---|
| Size / dim | ~568M, 1024-d | ~596M, 1024-d |
| License | MIT | Apache 2.0 |
| Context | 8192 tokens | 32k tokens |
| Strengths | Dense + sparse + ColBERT outputs; sparse weights suit exact English terms inside Urdu sentences | Instruction-aware queries, flexible output dimensions |
| Query prompt | None | Task instruction on the query side only |

- **Ruled out:** Qwen3-Embedding-8B (too big for 8 GB VRAM).
- **No published Urdu or code-switched benchmark exists** for either model, so a measured bake-off on your own data replaces picking from leaderboards.
- **Default lean:** BGE-M3, because its sparse weights can be reused later by the hybrid router. A tie goes to BGE-M3.

### The three tests

| Test | What it measures | Status |
|---|---|---|
| **A** | Question → correct lecture moment (Recall@1/3/5, MRR) | **Done** |
| **B** | Lecture concept → textbook page (±2 pages) | Blocked: textbook not chosen |
| **C** | English concept summaries instead of raw Urdu-script text | Blocked: needs Ollama concept extraction |

---

## 5. How Test A was set up

### Environment (all inside WSL Ubuntu-24.04, project at `E:\FYP\embedding`)

- Cache variables point to `/mnt/e/FYP/cache/` (`HF_HOME` → `huggingface`, `PIP_CACHE_DIR` → `pip`, `TORCH_HOME` → `torch`).
- A virtual environment at `/mnt/e/FYP/embedding/.venv`.
- torch 2.11.0+cu128 (CUDA available), transformers 5.18.0, sentence-transformers 6.1.0, faiss-cpu 1.15.1, numpy, pandas, pytest. Pinned in `requirements.lock.txt`.
- Model weights (about 3.4 GB) downloaded once into the E: cache; later runs use `HF_HUB_OFFLINE=1`.

### The work was split between you and an Antigravity agent

| Who | Did what |
|---|---|
| Agent | Environment setup, wrote `embed_bakeoff.py` and its unit tests, verified with a synthetic fixture, ran the bake-off, wrote the analysis drafts |
| You | Located and copied the SRT, wrote/approved the query file, made every approval decision, will make the final model call |

Prompt design rules that were followed:

- The agent had to stop and ask before downloads, `sudo`, torch installs and Ollama stops.
- The agent must not draft queries from the SRT (that would make the test circular).
- The real SRT was never used for verification; a synthetic fake lecture was.

### Data

- **Lecture:** *100 Days of Machine Learning, Day 4: Batch vs Online Learning*.
- **File used:** `/mnt/e/FYP/embedding/data/day04_batch_vs_online/whisper_urdu.srt`, copied from `...\FYP Testing\data\transcripts\day04_batch_vs_online\`. The copy under `eval\` was confirmed byte-identical (same SHA-256).
- **Size:** 640 cues, 687.92 seconds (11:28).
- **Script mix:** about 44.8% Arabic-script and 55.2% Latin letters by character count, which is consistent with Urdu sentences full of English technical terms. A visual check of the pasted transcript showed no Roman Urdu in the corpus.

### Script design (`tools/eval_embeddings/embed_bakeoff.py`)

- Whisper SRT parsed without extra dependencies; text preserved exactly (no transliteration, no case-folding).
- Windows of 30, 60 and 90 seconds, non-overlapping. Each window's scoring span is the fixed slot `[k*stride, k*stride + W)`; only the last window is clipped to the transcript end.
- Models loaded in FP16 on CUDA; embeddings L2-normalised; exact FAISS `IndexFlatIP` retrieval.
- **Qwen3 query side only** gets the instruction: `Instruct: Given a question about a lecture, retrieve the lecture transcript passage that answers it` followed by `Query: `. Documents are embedded plain. BGE-M3 uses no prompt.
- **A hit** means the retrieved window strictly overlaps the labelled time range.
- Metrics: Recall@1/3/5, MRR, embedding time, peak VRAM, truncation counts. Outputs include `per_query_results.csv`, `summary.csv`, `summary.md`, `run_config.json`.
- Verified by 7 passing unit tests, a dry run, a real-model smoke test on the fake fixture, and an offline reload check.

### The query set (`tools/eval_embeddings/queries.csv`)

- **28 queries:** 15 `en`, 8 `hard` (paraphrases avoiding the lecturer's exact words), 5 `roman` (Roman Urdu stress test).
- Ranges are tight (10 to 37 seconds each), within the lecture length, and none exceeds 25% of the lecture.
- Three pairs intentionally ask about the same passage in different forms (English, paraphrase, Roman Urdu), so the queries are **not statistically independent**.
- **Important honesty note:** the time ranges were taken from the Whisper timestamps and not from your own hand-transcribed reference. This leans labels slightly toward passages Whisper transcribed well. You were asked to spot-check about 8 ranges against the audio (see Section 9).

---

## 6. Results

### 6.1 A mistake that was caught and corrected

The first run used a 512-token limit that **I** set in the script spec. It truncated Qwen3's windows (2 at W60, 7 at W90), which made BGE-M3 look ahead. A rerun with a 1024-token limit removed all truncation, and Qwen3 gained 2 hits at W60 and 1 at W90. **The first run's analysis is therefore outdated; use only the 1024 run (`results_seq1024/`).**

### 6.2 Final results (1024-token run, 28 queries)

| Model | Window | Windows in lecture | Chance Recall@3 | Recall@1 | Recall@3 | Recall@5 | MRR | Peak VRAM (MB) |
|---|---|---|---|---|---|---|---|---|
| BGE-M3 | 30 s | 23 | 13.0% | 57.1% (16/28) | 92.9% (26/28) | 96.4% | 0.730 | 1,141.7 |
| BGE-M3 | 60 s | 12 | 25.0% | 67.9% (19/28) | 89.3% (25/28) | 96.4% | 0.801 | 1,160.8 |
| BGE-M3 | 90 s | 8 | 37.5% | 64.3% (18/28) | 92.9% (26/28) | 100% | 0.790 | 1,161.5 |
| Qwen3-0.6B | 30 s | 23 | 13.0% | 46.4% (13/28) | 89.3% (25/28) | 92.9% | 0.674 | 1,766.5 |
| Qwen3-0.6B | 60 s | 12 | 25.0% | 67.9% (19/28) | 92.9% (26/28) | 96.4% | 0.799 | 2,044.5 |
| Qwen3-0.6B | 90 s | 8 | 37.5% | 67.9% (19/28) | 92.9% (26/28) | 96.4% | 0.817 | 2,044.5 |

Recall@3 at W30 by query kind:

| Model | `en` (15) | `hard` (8) | `roman` (5) |
|---|---|---|---|
| BGE-M3 | 15/15 | 8/8 | 3/5 |
| Qwen3-0.6B | 13/15 | 8/8 | 4/5 |

### 6.3 What the results say

- **The two models are tied.** At every window the gap is 1 to 2 queries, which the pre-set noise rule treats as a tie. The pre-set decision rule (a clear winner needs at least 3 more top-3 hits on the `hard` + `roman` subset, and no worse than 2 behind on `en`) gave 12/13 vs 12/13 at each model's best window (W90), so the **default branch applied: BGE-M3**.
- **Best-window rule applied at W90, but W30 gives the same verdict:** at W30 the gaps are 1 (hard+roman, Qwen ahead) and 2 (`en`, BGE-M3 ahead). Still a tie.
- **Reasons BGE-M3 is kept (secondary criteria only):** a tie goes to BGE-M3 by the plan; its sparse weights can be reused in the planned hybrid router; lower VRAM (about 1.1 GB vs 1.8 to 2.0 GB).
- **No tokenizer or truncation advantage can be claimed for BGE-M3.** At 1024 tokens neither model truncates anything.
- **Weak spot:** the Roman Urdu retraining question (CSV row 25) missed top-3 for both models at every window (ranks 6 to 15), while its English twin ranked 1st or 2nd. The explanation (Roman Urdu vs native-script mismatch) is a **hypothesis**, based on one query out of five.
- **Two queries flagged earlier as possible bad labels were fine:** at W30 and W60 both rank first for both models; only the 90-second window caused their misses.

---

## 7. Decisions made

| # | Decision | Reason |
|---|---|---|
| 1 | **Embedding model: `BAAI/bge-m3`** | Tie on accuracy; wins on the tie-break (sparse weights for the router, lower VRAM) |
| 2 | **Window size: 30 seconds** | Smallest window within 2 queries of the best; only about 13% chance level vs 37.5% at 90 s, so the same score means far more; gives a 30-second citation instead of a 90-second one |
| 3 | **Do not use W90** | Only about 8 windows in the lecture, so a top-3 hit is easy; too coarse to jump to |
| 4 | **Index design:** flat inner-product FAISS on normalised vectors | One video plus one textbook is only a few thousand vectors |
| 5 | **Dual index (planned):** raw transcript windows plus English concept summaries | Summaries make page fusion more robust |
| 6 | **Never embed Roman Urdu** | Keep it for WER evaluation; embed the native-script Whisper output |
| 7 | **Embed windows, not single subtitle lines** | About 30 to 60 seconds of speech per chunk |
| 8 | **Reranker should match the embedding family** | Family to be confirmed, not yet evaluated; no specific model is named in the documents |
| 9 | **UI shows the top 3 results (or uses a reranker)** | At W30 the correct window is first only about 57% of the time, but is in the top 3 about 93% of the time |
| 10 | **Qwen3 query-side instruction only** | Documents embedded plain |
| 11 | **The agent recommends; you decide** | Final model call stays with you |

---

## 8. Honest limits (to state in the defense)

1. One 11-minute lecture and 28 queries, so small differences are noise.
2. Several queries intentionally target the same passage, so they are not independent.
3. Labels were derived from Whisper segment timestamps; say "spot-checked against the audio" **only if you actually did that**, otherwise say "not independently verified".
4. Queries are English and Roman Urdu, tested against native-script Whisper output; the Roman Urdu result is five queries and is a limitation, not a finding.
5. The tie means BGE-M3 was kept on secondary criteria, not because it was shown to be more accurate.

Suggested defense line: *"The first run suggested a gap, but rechecking showed it came from a sequence limit that truncated the other model's windows. After fixing it the models tied, so we kept BGE-M3 on secondary criteria and chose 30-second windows because they are far more informative than chance at that granularity."*

---

## 9. What is still to do

### A. Your actions

| # | Action | Where | Why |
|---|---|---|---|
| 1 | Spot-check about 8 labelled ranges against the audio (mostly `hard`, `roman` and the 10 to 12 second ones); fix any that are off | `tools/eval_embeddings/queries.csv` | Labels came from Whisper timestamps; a wrong label makes a good model look bad. If you change any row, rerun the bake-off |
| 2 | Read the misses yourself | `results_seq1024/per_query_results.csv` | Only you can judge why a query missed |
| 3 | Apply the documentation updates (see 9B) | Features doc and proposal | Keep documents consistent |
| 4 | Recompile the proposal | `Final_Proposal.tex` | Check the table and new bullet render |

### B. Documentation updates (draft in `tools/eval_embeddings/results/doc_updates.md`)

Apply these edits **before pasting**:

1. **Section 5.3:** replace "statistically significant" with a statement that neither model led by the pre-set margin of 3 or more hits at its best window.
2. **Defense note:** replace "hybrid BM25/dense router" with "the planned hybrid router".
3. **Table 3:** change "sparse lexical weights retained" to "sparse weights reserved for the hybrid router".
4. **Section 9.1:** replace "preventing out-of-memory errors" with "keeping the pipeline within the 8 GB budget".
5. **Labels sentence:** match it to whether you really spot-checked.
6. **Defense note:** say that 12/13 and 14/15 are the W90 counts; add the W30 counts (BGE-M3 11/13 and 15/15, Qwen3 12/13 and 13/15).
7. **LaTeX:** add `\usepackage{amsmath}` (for `\text` in the math), and shrink the six-column table (`\small` or `\resizebox`).
8. **Add one sentence** about chance level (13% at 30 s vs 37.5% at 90 s) and split the long 5.3 paragraph into shorter ones.

| Edit goes in | Section | Change |
|---|---|---|
| `Insightex_Final_Features.md` | F (GPU rotation bullet) | Three committed models: Whisper, Ollama LLM, embedding model, plus optional PaddleOCR |
| `Final_Proposal.tex` | 9.1 (VRAM risk) | One bullet: embedding model peak about 1.2 GB, own stage, never alongside the other models |
| `Final_Proposal.tex` | 5.3 (retrieval evaluation) | Results paragraph and table for all three windows, plus the limits |
| `Final_Proposal.tex` | Table 3 (tools) | Embeddings row; planned reranker row |

### C. Later technical work

| Item | Depends on | Notes |
|---|---|---|
| **Test B** (lecture concept → textbook page, ±2 pages) | A chosen textbook with page-aware chunks | Same script, different corpus; this is the Feature 1 exit criterion |
| **Test C** (English concept summaries vs raw Urdu-script text) | Ollama concept extraction (Milestone 3) | Compare against Test A |
| **Reranker** | Embedding choice (done) | Pick the family, confirm the exact model, evaluate |
| **Milestone 4 FAISS build** | Window choice (done) | Use W30, flat inner-product index on normalised BGE-M3 vectors |
| **More queries** | Optional | Add queries if a close result needs resolving; Roman Urdu especially has too few |

---

## 10. File and folder map (`E:\FYP\embedding`)

| Path | What it is |
|---|---|
| `.venv/` | Python environment |
| `requirements.lock.txt` | Pinned package versions |
| `data/day04_batch_vs_online/whisper_urdu.srt` | The lecture transcript used |
| `tools/eval_embeddings/embed_bakeoff.py` | The bake-off script |
| `tools/eval_embeddings/test_bakeoff.py` | Unit tests |
| `tools/eval_embeddings/selftest/` | Synthetic fixture used only for verification |
| `tools/eval_embeddings/queries.csv` | The 28 labelled queries |
| `tools/eval_embeddings/results/` | First run (512 limit; **outdated**), plus `window_comparison.md`, `analysis.md` and `doc_updates.md` |
| `tools/eval_embeddings/results_seq1024/` | **Final run (1024 limit); use this for all numbers** |

Reproduce the final run (offline):

```bash
wsl -d Ubuntu-24.04 -- bash -lic "source /mnt/e/FYP/embedding/.venv/bin/activate && cd /mnt/e/FYP/embedding && HF_HUB_OFFLINE=1 python tools/eval_embeddings/embed_bakeoff.py --srt /mnt/e/FYP/embedding/data/day04_batch_vs_online/whisper_urdu.srt --queries tools/eval_embeddings/queries.csv --out tools/eval_embeddings/results_seq1024 --max-seq-length 1024"
```

---

## 11. Things to remember (gotchas)

- Use only the 1024-run numbers. The first run's `analysis.md` and `summary.csv` are outdated.
- The agent's chat summary once reported identical MRR for both models at W90 (0.887). That was wrong; the file shows 0.790 (BGE-M3) and 0.817 (Qwen3). **Always trust the files over the chat summary.**
- The agent's first draft of the document updates used the W90 hit counts under a W30 decision; check that every number is tied to the right window.
- Never let an agent write labelled ranges from the SRT without your spot-check, or say the labels were "hand-labelled".
- Run commands inside the WSL shell, not nested through PowerShell (quoting breaks `$` and `&&`).
- Free VRAM first (`ollama ps`, then `ollama stop <model>`) before any GPU run.
