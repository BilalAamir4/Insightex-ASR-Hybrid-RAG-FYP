# ADR-0047: M6 ask box and citations

Status: Accepted
Date decided: 2026-10-14
Date recorded: 2026-10-14
Module: M6

Builds the user-facing search of M5: an ask box on the player page that shows citations. It applies ADR-0045 (retrieval configuration) and ADR-0046 (question rewrite). No LLM writes an answer here; that is M11.

## Context

M5 left a search endpoint that returns ranked windows with scores for tools (`POST /api/lectures/{id}/search`), a rewrite fix for Roman Urdu questions that passed gate G5 (ADR-0046), and a citation rule (ADR-0044): a citation seeks to the first transcript segment inside the window. The question length, the number of citations, the warm-up of the rewrite model, the privacy of questions, the GPU-lease behaviour of the rewrite call and the metrics have to be fixed before code.

## Decision

- **Citation.** Rank 1 to 3 and the window's time range as `mm:ss-mm:ss`, clickable. No transcript text, no score, no gist (a gist is decided in M11). Clicking calls `seekTo(seek_s)`, where `seek_s` is the start of the first transcript segment inside the window. `windows.json` stores it as `first_segment_start`, written when the index is built (windows schema version 2), so the query path never opens the transcript. Three citations come from the final list after de-duplication (ADR-0043: de-duplicate, then take the top 3).
- **Endpoint.** `POST /api/lectures/{id}/ask` with `{"question": str}` returns `{"lecture_id", "index_config_id", "citations": [{"rank", "start", "end", "seek_s"}], "rewrite": {"used": bool, "fallback_reason": str | null}}`. The existing `/search` endpoint stays as the raw retrieval primitive for the evaluation tools and does not change.
- **Question limit.** 1 to 300 characters after trimming (it matches the 300-character bound of the rewrite schema), checked in the UI and the API. The API answers `400` with the codes `QUESTION_EMPTY` or `QUESTION_TOO_LONG` and never echoes the question back.
- **Search flow.**
  1. Rewrite the question as ADR-0046 specifies (the 2 s timeout and the original-only fallback are in that ADR).
  2. Rank every window of the lecture for the original question, and for the rewrite when there is one: the candidate depth of each ranking is the whole index (as in G5), each question encoded alone on the CPU in float32.
  3. With a rewrite, fuse the two rankings with Reciprocal Rank Fusion, k=60, ties by smaller window id: exactly the function and parameters of the G5 harness. A replay test feeds the 47 recorded G5 rewrites through the production code and asserts the fused rankings and scores of `docs/evidence/m6/g5_B_fused.json`.
  4. De-duplicate (any overlap above `retrieval.dedupe_min_overlap_s`), take the top `retrieval.citations` (3).
- **Rewrite request.** Built by one function from the settings and the prompt file `config/prompts/query_rewrite_v1.txt`, whose sha256 is pinned in `retrieval.rewrite_prompt_sha256` (a mismatch disables the rewrite and logs an error: a changed prompt needs a new ADR and a new gate). The body is the one the G5 harness sent: keys in the same order, `think` false, `temperature` 0, the ADR's literal JSON schema, `seed`, `keep_alive`, `num_ctx` and the model from the `ollama:` settings, `num_predict` from `retrieval.rewrite_num_predict` (64). The Ollama client gets a low-level call that sends a prebuilt body, with no `/api/tags` check per call. A test asserts that the serialised production body is byte-identical to the body built by the G5 harness, and to a golden file captured from the gated version of the harness. The G5 usability checks are reimplemented identically and checked against the 47 recorded responses.
- **Fallback reasons** (the search then uses the original question only): `rewrite_disabled` (config off or prompt hash mismatch), `gpu_busy` (a job holds the exclusive GPU lease), `llm_not_loaded` (the model is not loaded in Ollama with the configured `num_ctx`; search never loads it), `llm_unreachable`, `timeout` (the call ran longer than `retrieval.rewrite_timeout_s`, 2 s, even if it finished), `unusable` (ADR-0046's unusable-output rules), `error`.
- **GPU lease.** The rewrite call holds the shared GPU lease for its duration (taken without waiting), so the worker cannot unload Ollama in the middle of a call. If the lease cannot be taken at once, the reason is `gpu_busy`. When `gpu.lease_enabled` is false there is no lease.
- **Warm-up.** `POST /api/lectures/{id}/warm-up` (202) is called by the player when it opens a searchable lecture. In a background thread the API takes the shared lease without waiting and, if it is free, asks Ollama to load the model with a chat request that has no messages and the same model, `keep_alive` and options (`num_ctx`, `temperature`, `seed`, `num_predict`) as the rewrite request, so Ollama does not reload for the first rewrite. If a job holds the lease the warm-up is skipped (`gpu_busy`); a second warm-up while one runs is skipped. Questions never wait for it; until the model is loaded, the original-only fallback applies.
- **Privacy.** No question and no rewrite text is persisted or logged. The API writes one JSON log line per question (logger `insightex.ask`, in `api.log`) with `total_ms`, `rewrite_ms`, `search_ms`, `rewrite_used`, `fallback_reason` and the number of citations; the warm-up writes `warm_up` lines with its result and reason. Validation errors never echo the input. The Ollama request log of the host stays off.
- **Lecture document.** `GET /api/lectures` and `/api/lectures/{id}` gain `searchable` (true when the lecture's index is current for the model and windows schema); the ask box is disabled until it is true.

## Alternatives considered

- **Change `/search` into the user endpoint.** The evaluation tools depend on its raw, un-deduplicated rankings and on `window_id` and `score`; a separate endpoint keeps the evidence reproducible.
- **Read `transcript.json` at query time for the seek time.** Opens a large file on the query path and spreads the transcript into the API; a field in `windows.json` costs one index rebuild.
- **Warm up on `GET /api/lectures/{id}`.** A read with side effects; an explicit call is clearer and testable.
- **Store question counts in SQLite.** More code and a schema for numbers that log lines already carry; revisit if the thesis evaluation needs aggregation.

## Consequences

- Questions can be shown nowhere after they are asked (no history); the evaluation of real use needs a separate, consented log if it is ever wanted.
- The Day 4 index is rebuilt once for `first_segment_start`; the ranks and scores must equal the committed evidence apart from the new field (checked in M6 session A).
- The first question after the model has been unloaded (by a job or by Ollama's own keep-alive) runs without the rewrite.

## Evidence

- `docs/evidence/m6/`: `rebuild_check.json` and the session A notes in its README; `m6_verify_<time>.json/.log` (13 checks on Day 4, 14 Oct 2026: all passed); `manual_checklist.md` (browser checks, to be signed).

## Gate / revisit when

Closes when `tools/m6_verify` passes and the manual browser checklist is signed. Revisit when M11 adds answers and when M9 runs Test A on more lectures.
