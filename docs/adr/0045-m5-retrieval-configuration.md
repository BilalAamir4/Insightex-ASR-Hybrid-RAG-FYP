# ADR-0045: M5 retrieval configuration: fixed 30 s windows, dense only, CPU fp32 questions

Status: Accepted; Roman Urdu open item amended by ADR-0046
Date decided: 2026-10-11
Date recorded: 2026-10-11
Module: M5

Amends ADR-0001: the 30 s window length stands; this ADR adds how windows are cut (fixed time grid, no overlap), that retrieval is dense only, and where questions are encoded.

## Context

ADR-0043 fixed the rules for the open M5 choices; ADR-0044 built the index stage. The gates were run on one lecture (Day 4, 23 windows, 47 gold questions); every number is provisional until Test A runs on more lectures in M9. The rules (hit at 50% of a gold span, de-duplication of any overlap, net count of wins minus losses >= 2 to adopt a candidate) and all per-query results are in ADR-0043 and `docs/evidence/m5/`.

## Decision

- **Windows: fixed 30 s time grid, stride 30 s (no overlap), segments assigned by their start time.** Segment-snapped windows (gate G3s) and a 15 s stride (gate G3) each tied the grid on the 24-query set (net -1 and net 0), so the simpler grid stays.
- **Retrieval: dense BGE-M3 only.** Adding BGE-M3's sparse head fused by RRF k=60 (gate G2) tied (net -1). The sparse code stays in `tools/eval_retrieval/` (`sparse.py`), verified against `BGEM3FlagModel`; FlagEmbedding is not installed in the project environment.
- **Questions are encoded on the CPU in float32, one at a time, in the API process; documents on the GPU in float16 at ingest.** Gate G1 passed: cosine between the GPU fp16 and CPU fp32 question vectors was at least 0.9999986 for all 47 questions and no question changed hit or miss. The encoder is loaded and warmed up when the API starts.
- **Open, not decided here:** gate G4 (Roman Urdu questions) returned "fix needed" (the Roman twin lost 3 more pairs than it won). A Roman Urdu fix is its own decision and has not been proposed or built.
- **English questions over native-script windows work well enough that per-window translation is not needed for M5** (ADR-0041's open question): English-only Recall@3 is 0.8696 (20 of 23 questions) at the final configuration.

## Alternatives considered

- Segment-snapped windows, 15 s stride, dense + sparse RRF: each measured in ADR-0043 (tied, so the simpler configuration stays).
- GPU question encoding: rejected by the VRAM contract (the GPU belongs to Ollama at query time); G1 shows the CPU path is equivalent on this lecture.

## Consequences

- Final configuration results (grid 30, dense, API CPU path, 47 questions): Recall@3 0.8085, MRR 0.6583; the 24-query gate set 0.8750 and 0.7097; English questions (A01 to A23) 0.8696 and 0.7261; Roman questions (24) 0.7500 and 0.5933.
- The API process holds about 2.3 GiB of RAM from startup (peak 2.41 GiB measured), question latency is about 50 ms median, 59 ms p95 over HTTP, and startup takes about 5 s longer.
- Re-evaluate on more lectures in M9: with 24 queries one flip is 4 points, and a net of 2 is the threshold.

## Evidence

- `docs/evidence/m5/` (README lists each file); `tools/eval_retrieval/score.py`.

## Gate / revisit when

Revisit when Test A runs on more lectures (M9), when the Roman Urdu decision is made, and if the reranker (M9) changes what the candidate list needs to contain.
