# ADR-0043: M5 retrieval gate rules

Status: Accepted
Date decided: 2026-10-11
Date recorded: 2026-10-11
Module: M5

Amends ADR-0041: its open question "cross-language search with English questions over native-script transcripts" is measured by gate G4 below, with the decision rule below.

## Context

M5 builds windowing, BGE-M3 embedding and FAISS retrieval (ADR-0001). Several design choices are still open (window stride, sparse fusion, CPU query encoding, Roman Urdu questions). The rules that decide them are fixed here, before any experiment runs, so no gate can be tuned after seeing its result. The rules on windowing and sparse fusion come from the M5 notes in `docs/BUILD_ORDER.md` (pending decisions) and are made concrete here.

## Decision

**Test data.** `tools/eval_retrieval/gold_spans.json`, frozen at commit `0f5e5ab` and never edited by M5. 47 queries on the Day 4 lecture; spans are in seconds; `pair_of` links 23 Roman Urdu twins to their partners. All results are provisional until Test A runs on more lectures in M9.

**Hit rule.** A retrieved window is a hit if it covers at least 50% of any one gold span of that query. Before taking the top 3, drop any window that overlaps a higher-ranked kept window by more than 0 s (windows that only touch at an edge do not overlap), so the top 3 are three distinct moments. (Amended 2026-10-11, before G3: the first draft dropped a window only when it overlapped a higher-ranked one by more than 50% of its own length; with a 15 s stride neighbours overlap by about 50%, so that rule would decide duplicates by segment-snapping noise.) Primary metric: Recall@3. MRR is reported alongside and never decides a gate.

**Net-count rule.** For configs A (current or simpler) and B (candidate), count per query wins (B hit, A miss) and losses (A hit, B miss). Adopt B only if wins - losses >= 2. Anything less is a tie, and a tie keeps A. Gates G2 and G3 use 24 queries: A01 to A23 plus A28. The `...r` twins and A24 to A27 (twins of A02, A20, A16 and A18) are excluded there because paired questions flip together; A28 has no twin and is independent. Recall@3 for the English-only set (sets `en` and `hard`) is reported at every gate, so absolute English performance stays visible.

**Gates, run in this order, each reported and approved before the next:**

- **G0 baseline.** Fixed 30 s windows, dense only, GPU encoding, run through production code. It is checked against the legacy bake-off encoder (restored from tag `import-baseline` into a scratch directory, not into the repo) by ranking, not by hits: the same window texts go through the legacy encoder and the production path (both GPU), and G0 passes if, for every query, the top-10 window order is identical and cosine scores match within 1e-4. Any differing query is reported. As a sanity check, the restored legacy scorer is first run on its own windows and its own hit rule and must reproduce the bake-off's recorded result. Production is then scored with the hit rule and gold above; that is the baseline G3 compares against.
- **G3s snapping** (added 2026-10-11, after G3 was first run). Snapping to Whisper segment boundaries is gated like any candidate: A = the G0 fixed 30 s time grid (simpler), B = 30 s windows snapped to segment boundaries, both with no overlap, dense only, on the 24 queries A01 to A23 + A28, same net-count rule. Snapping was first adopted without evidence; the earlier "decided" status is withdrawn.
- **G3 windows.** Run on the G3s winner: no overlap (A) against 15 s stride (B). Dense only. If G3s keeps the grid, G3 is A = grid stride 30 s against B = grid stride 15 s.
- **G2 sparse.** On the G3 winner, dense only (A) against dense + sparse fused with Reciprocal Rank Fusion, k=60 (B). The sparse side is the BGE-M3 sparse head (ReLU of the model's `sparse_linear` over the last hidden state, the largest weight per token id, special tokens excluded, scored by the sum of weight products over shared token ids), implemented in `tools/eval_retrieval/sparse.py` on the existing transformers stack and verified against `BGEM3FlagModel` before the gate runs: for all windows and gold questions the sparse weights must match within 1e-4 and the dense vectors must have cosine >= 0.9999 with the reference's. The FlagEmbedding package is not installed in the project environment; the reference check runs in a throwaway virtual environment. The dense ranking in B is the same as in A (the G3 winner's index); only the sparse ranking is added. If B ties, keep dense only, leave the sparse code in `tools/`, and the report drops the sparse tie-break claim.
- **G1 CPU queries.** On the final config, queries encoded on CPU (fp32) against GPU. Equivalence gate: pass if every query's dense cosine(CPU, GPU) >= 0.999 and no query changes hit or miss. Any failure: stop and report; no default is chosen.
- **G4 Roman Urdu.** On the final config, over the 23 pairs, Roman twin against its partner. If the Roman side loses 2 or more net, a Roman Urdu fix is needed and becomes its own decision (not built in M5). Recall@3 is reported for the English and Roman sets separately. This replaces the "fails to retrieve" trigger for English questions in ADR-0041 and `docs/BUILD_ORDER.md`.

**Scope.** Production code: windowing, dense (and sparse only if G2 passes) encoding on GPU at ingest, a FAISS index per lecture in the workspace, query encoding on CPU in the API process. The evaluation scorer lives in `tools/eval_retrieval/`, imports nothing from `backend/src`, and calls production code only through the CLI or API.

## Alternatives considered

- **Hit by any overlap (the bake-off rule).** Rewards windows that touch a span by a fraction of a second, which gets easier as windows grow.
- **Drop a window only when it overlaps a higher-ranked one by more than 50%.** With a 15 s stride the overlap of neighbours sits at about 50%, so the outcome would depend on where segment edges fall.
- **Adopt B on any improvement.** With 28 queries one flip is 3.6 points of Recall@3, which is within noise; the net >= 2 rule requires a margin.
- **Include twins (and A24 to A27) in G2 and G3.** A question and its Roman twin usually flip together, so they would count one effect twice.

- **Snapping windows to Whisper segment boundaries (gate G3s, run 2026-10-11).** Definition used: a window starts at a segment start and ends at the segment end closest to start + 30 s (ties to the earlier segment); its time range is the first segment's start to the last segment's end, so silence between windows is not covered; next window starts at the segment after the last one included (stride 30 s). Result on the 24 queries A01 to A23 + A28, dense only, GPU fp16 queries: grid Recall@3 0.8750, MRR 0.7097; snapped 0.8333, 0.7198; wins 0, losses 1 (A17), net -1, a tie, so the grid stays. Evidence: `docs/evidence/m5/idx_grid30.json`, `idx_snapped30.json`. Other snapping definitions (nearest boundary with a minimum length, merging short tails) were not tried.
- **Gate G3 on the grid (2026-10-11).** Stride 30 s (A) against 15 s (B), grid windows, same 24 queries: Recall@3 0.8750 both, MRR 0.7097 against 0.7431; wins A12, A23, losses A07, A11, net 0, a tie, so stride 30 s with no overlap stays. Evidence: `idx_grid30.json`, `idx_grid15.json`. (An earlier G3 run on snapped windows, `g3_A.json` and `g3_B.json`, gave net +1, also a tie.)

## Consequences

- Every adoption in M5 is a net count on named queries, not a judgement on a mean.
- The first 28 ids contain five Roman queries (A24 to A28); A24 to A27 are twins of A02, A20, A16 and A18, so G2 and G3 exclude them (24 queries). This amendment was made before any experiment ran.
- A tie always keeps the simpler config, so sparse retrieval and 15 s stride can only enter with measured evidence.

## Evidence

- Per-query results with the index fingerprint of the index that produced them: `docs/evidence/m5/` (see its README).
- Gold: `tools/eval_retrieval/gold_spans.json` at `0f5e5ab`. No result exists yet; this ADR is written before any experiment.

## Gate / revisit when

Revisit after Test A runs on more lectures in M9: the rules (not only the results) may be tightened when the query set is larger.
