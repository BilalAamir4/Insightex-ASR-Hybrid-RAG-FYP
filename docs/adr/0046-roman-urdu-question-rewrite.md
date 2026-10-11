# ADR-0046: Roman Urdu questions: rewrite every question into English at query time

Status: Proposed
Date decided: 2026-10-11
Date recorded: 2026-10-11
Module: M6

Resolves the open item of ADR-0045 (gate G4 returned "fix needed"). No code is written by this ADR.

## Context

Gate G4 (ADR-0043, `docs/evidence/m5/g4_pairs.txt`) compared each Roman Urdu question with its English twin on the final configuration (fixed 30 s grid, dense only, CPU fp32 questions): over 23 pairs the Roman side won 0 and lost 3 (A25, A19r, A22r), net -3. Recall@3 over the pairs was 0.8696 for English partners and 0.7391 for Roman twins; over the full sets 0.8696 (English, 23) and 0.7500 (Roman, 24). Documents are never romanised (ADR-0001), so a Roman Urdu question is matched against native-script windows. All figures are for one lecture and are provisional until M9.

## Decision

- **Fix: rewrite the question into English with the LLM at query time.** Every question is rewritten, not only those that look like Roman Urdu: temperature 0, the question only as input (no lecture text), technical terms kept as they are, a one-line English question as output. The Ollama call follows the call contract of ADR-0002 (`num_ctx` explicit, `think` false, `num_predict` explicit, token budget checked).
- **Search runs on both the original question and the rewrite**, and the two rankings are fused with Reciprocal Rank Fusion, k=60 (the same fusion as the sparse test in ADR-0043).
- **If the LLM is not loaded, search uses the original question only.** The rewrite never blocks or delays an answer beyond its own latency; a failed or timed-out rewrite falls back the same way.
- **Built in M6**, reusing M6's LLM client and the shared GPU lease for Ollama calls (the GPU belongs to Ollama at query time).
- **Status stays Proposed until gate G5 passes;** if G5 fails, the question path keeps the original-only search and Roman Urdu stays a documented limitation or gets a new decision.

## Gate G5 (pre-registered, before any rewrite has been run)

Configuration: fixed 30 s grid, stride 30 s, dense, CPU question encoding (the production path, ADR-0045). Same hit rule, de-duplication and net-count rule as ADR-0043; A = original question only, B = original + rewrite fused.

- **Roman set (24 questions: A24 to A28 and the 19 `...r` twins):** adopt B only if wins - losses >= 2.
- **English set (23 questions: A01 to A23):** B must not lose 2 or more net against A.
- **Latency:** the added time per question (the rewrite call plus the second search), reported as median and p95 over the 47 questions; p95 must be <= 2 s.
- **Evidence:** every rewrite (question id, original, rewrite) is logged in `docs/evidence/` for human review. The rewrites are read by a person; a bad rewrite is reported, not removed or re-run to improve the result.
- Provisional until Test A runs on more lectures (M9).

## Alternatives considered

- **Translate or romanise the windows at ingest (per-window English text).** Costs an LLM pass over every lecture, adds a lossy step before search, and ADR-0041 keeps transcripts in the spoken language; measured only if the question-side fix fails.
- **Rewrite only questions detected as Roman Urdu.** Needs a detector with its own errors; rewriting every question lets G5 measure the English cost directly.
- **Replace the original with the rewrite.** A bad rewrite would lose a question that already worked; fusing keeps the original ranking as a vote.
- **A multilingual query encoder or fine-tuning:** no evidence they help, and the embedding model is decided (ADR-0001).

## Consequences

- Query time gains one Ollama call (and a loaded model when the LLM is in use); with Ollama unloaded the search is the G4 baseline.
- An extra LLM prompt and its failure modes belong to M6; the rewrite text is internal and never shown (ADR-0041 only concerns transcripts, but the rewrite is not an answer either).

## Evidence

- Problem: `docs/evidence/m5/g4_pairs.txt`, `g4_api_cpu_fp32.json`. G5 evidence will be added under `docs/evidence/m6/` when it is run.

## Gate / revisit when

G5 as above. Revisit when Test A runs on more lectures (M9), and if the CPU reranker (planned, M9) changes what the candidate list needs.
