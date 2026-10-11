# ADR-0046: Roman Urdu questions: rewrite every question into English at query time

Status: Accepted
Date decided: 2026-10-11
Date recorded: 2026-10-11
Module: M6

Resolves the open item of ADR-0045 (gate G4 returned "fix needed"). No code is written by this ADR.

## Context

Gate G4 (ADR-0043, `docs/evidence/m5/g4_pairs.txt`) compared each Roman Urdu question with its English twin on the final configuration (fixed 30 s grid, dense only, CPU fp32 questions): over 23 pairs the Roman side won 0 and lost 3 (A25, A19r, A22r), net -3. Recall@3 over the pairs was 0.8696 for English partners and 0.7391 for Roman twins; over the full sets 0.8696 (English, 23) and 0.7500 (Roman, 24). Documents are never romanised (ADR-0001), so a Roman Urdu question is matched against native-script windows. All figures are for one lecture and are provisional until M9.

## Decision

- **Fix: rewrite the question into English with the LLM at query time.** Every question is rewritten, not only those that look like Roman Urdu: temperature 0, the question only as input (no lecture text), technical terms kept as they are, a one-line English question as output. The Ollama call follows the call contract of ADR-0002 (`num_ctx` explicit, `think` false, `num_predict` explicit, token budget checked).
- **Search runs on both the original question and the rewrite**, and the two rankings are fused with Reciprocal Rank Fusion, k=60 (the same fusion as the sparse test in ADR-0043).
- **If the LLM is not loaded, search uses the original question only.** Search never loads the model for a rewrite. In production the rewrite call has a **timeout of 2 seconds** (a tunable, `retrieval.rewrite_timeout_s`, added to `config/default.yaml` in M6); a rewrite that fails, returns nothing usable, or takes longer than the timeout is dropped and search uses the original question only, so an answer is never delayed by more than the timeout.
- **Rewrite call settings, fixed for G5 and production** (pre-registered 2026-10-11 before any rewrite was run; a change is a new ADR and a new G5):
  - **Model and call:** the project's Ollama model (`ollama.model`, currently `qwen3.5:latest`) through `insightex.llm.ollama_client.chat_json` (ADR-0002): `/api/chat`, `think: false`, `temperature` 0, `num_ctx` 8192 (the project default, so Ollama does not reload the model), `num_predict` **64** (maximum output tokens), `keep_alive` as configured.
  - **Messages:** one system message, the exact text of `config/prompts/query_rewrite_v1.txt` (sha256 `edac0394acc27081d904a35c85ac163d5e1011c7e1414b3888d2c59cff32744e`, copied below), and one user message that is the question exactly as the user typed it.
  - **Output format:** the JSON Schema `{"type": "object", "properties": {"english_question": {"type": "string", "minLength": 1, "maxLength": 300}}, "required": ["english_question"], "additionalProperties": false}`.
  - **Unusable output (counts as a failure in G5, and falls back to the original question in production):** an error or timeout; `done_reason` other than `stop` (including `length`, a cut-off at 64 tokens); output that is not valid JSON for the schema; an empty or whitespace-only `english_question`; a newline inside it; or any `<think>` or `</think>` text anywhere in the response (content or the thinking field).

  Prompt text (system message, v1, line breaks as in the file):

  > You rewrite one question about a lecture into one English question. The
  > question may be in English, in Roman Urdu or Hindi written in Latin
  > letters, in Urdu or Hindi script, or a mix of these. Keep the full
  > meaning: do not add, remove or change any information, and keep phrases
  > such as "according to the lecturer". Keep technical terms, names and
  > numbers exactly as they are (for example gradient descent, database,
  > Python, 10 GB). If the question is already in English, return it
  > unchanged. Do not answer the question. Return the English question as a
  > single line in the english_question field, with no explanation.

  An earlier draft of this prompt (sha256 `355096d0…a12324c`) was replaced on 2026-10-11 before any rewrite was run, because its examples (batch learning, server, Netflix, 24 hours) were taken from the test lecture. The replacement uses examples from outside it (gradient descent, database, Python, 10 GB) and also covers Urdu and Hindi script and the phrase "according to the lecturer".

- **Built in M6**, reusing M6's LLM client and the shared GPU lease for Ollama calls (the GPU belongs to Ollama at query time).
- **Accepted 2026-10-11 after gate G5 passed all four conditions (result below); provisional until M9** (one lecture, 24 Roman questions, net exactly +2). Had G5 failed, the question path would have kept the original-only search.

## Gate G5 (pre-registered, before any rewrite has been run)

Configuration: fixed 30 s grid, stride 30 s, dense, CPU question encoding (the production path, ADR-0045). Same hit rule, de-duplication and net-count rule as ADR-0043; A = original question only, B = original + rewrite fused.

- **Roman set (24 questions: A24 to A28 and the 19 `...r` twins):** adopt B only if wins - losses >= 2.
- **English set (23 questions: A01 to A23):** B must not lose 2 or more net against A.
- **Latency:** the added time per question (the rewrite call plus the second search), reported as median and p95 over the 47 questions; p95 must be <= 2 s. (The rule that no rewrite call may take longer than 2 s, below, already implies that the p95 of the rewrite call alone is <= 2 s; this figure also includes the second search, about 50 ms, and is kept as a separate, reported condition.) G5 runs with the model already loaded and warmed (the warm-up call is not counted) and with **no timeout**, so the true rewrite latency is measured.
- **Timeout and failure count:** separately from the latency figures, report how many of the 47 questions would have hit the production timeout (a rewrite call longer than 2 s) or failed (error, empty or unusable output). **G5 passes only if that count is 0;** if it is not, report and stop (no adoption decision, no tuning of the timeout or the prompt).
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

## G5 result (run 2026-10-11, Day 4 lecture, grid 30 dense index `56d5cbf47e45`, prompt sha256 `edac0394...2744e`)

- Roman set (24): Recall@3 0.7500 -> 0.8333, MRR 0.5933 -> 0.6073; wins A03r, A19r, A23r; loss A28; net +2 (threshold >= 2: met).
- English set (23): 0.8696 -> 0.8696; 0 wins, 0 losses (22 of 23 rewrites were identical to the question; A01 differs only in its quote marks).
- Rewrite call latency: median 0.45 s, p95 0.54 s, max 0.55 s. Added per question (rewrite + second search): median 0.51 s, p95 0.60 s, max 0.61 s (limit 2 s).
- Calls over 2 s or unusable: 0 of 47.
- All 47 rewrites are in `docs/evidence/m6/g5_rewrites.md` for review.

## Known prompt issues (for a possible v2; do not tune on these 47)

- A12r is garbled: the question mixes "am taur par" and "kitni bar" and the rewrite ("In what way do people retrain batch learning models how many times?") changed what it asks.
- A10r lost its subject ("why does not use batch learning?").
- Five rewrites added "according to the lecturer" or "the lecturer says" where the question had none (A28, A01r, A06r, A09r, A14r), against the "do not add" instruction; this may be the cause of the A28 loss.

A v2 prompt is evaluated only on the new lectures of M9, never tuned on these 47 questions, and is adopted only by a new ADR and a new G5-style gate.

## Harness deviation (accepted)

The G5 harness (`tools/eval_retrieval/g5_rewrite.py`) sent the Ollama request itself rather than through `chat_json`, because a standalone tool cannot import backend code and `chat_json` builds its `format` from a pydantic model. **M6 requirement:** a test asserts that the production rewrite request body (model, messages with the prompt file's text and its sha256, `think`, `format` schema, `keep_alive`, and every option: `num_ctx`, `temperature`, `seed`, `num_predict`) is byte-identical (same canonical JSON) to the body the G5 harness builds for the same question, so production runs exactly what was gated. The production code must therefore send the ADR's literal JSON Schema.

## Evidence

- Problem: `docs/evidence/m5/g4_pairs.txt`, `g4_api_cpu_fp32.json`. G5 evidence: `docs/evidence/m6/` (README there lists the files).

## Gate / revisit when

G5 as above. Revisit when Test A runs on more lectures (M9), and if the CPU reranker (planned, M9) changes what the candidate list needs.
