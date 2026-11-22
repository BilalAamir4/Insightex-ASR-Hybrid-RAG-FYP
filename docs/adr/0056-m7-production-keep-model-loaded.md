# ADR-0056: M7 Session 3 decision (a): keep Gemma loaded between extract-stage calls, only if Day 4 replies stay byte-identical

Status: Proposed
Date decided: not decided (draft 2026-11-22, for Bilal's review before any run)
Date recorded: 2026-11-22
Module: M7

Decision (a) of M7 Session 3 (handoff 5, item 1). It sets, before any run, the test that decides whether the production `extract` stage may keep the model loaded between its single-window calls, instead of reloading it for every call (ADR-0054 decision 2). Nothing in this ADR has been run. It uses the Day 4 lecture only; the held-out lecture `yt-5vqk6HnITko` is not used.

## Context

- **Reload per call is the frozen setting.** `extract.stage.keep_alive` is 0 (ADR-0054 decision 2), as in every M7 run (ADR-0049 decision 6). It is part of the stage fingerprint.
- **It is the main cost.** About 6.3–7.1 s of every ~9 s window is the model load (M7 report section 5). Day 4 at stage v2 took 179.6 s for 23 windows; `yt-B7TQYJLfYZQ` took 233.1 s for 28 (both measured, Session 3).
- **Why reload per call was chosen.** On synthetic input, Gemma's replies at temperature 0 depended on session state: a request repeated in the same loaded session changed its reply, with the draft model on and also off. After a fresh load, replies were reproducible (ADR-0049 "Gemma's session-state dependence"). The likely cause, prompt-cache reuse between calls, is **unverified**. So the prior evidence predicts that this test may well fail; it is run because the speed-up is large and the earlier evidence is synthetic, not Day 4.
- **What depends on reproducibility.** ADR-0054 decision 5 reuses a stored reply after a crash because "a repeated request returns a byte-identical reply". The request-identity test compares the stage's request with the harness's with `keep_alive` equal (both 0).
- **v2 published no raw replies.** The Day 4 stage v2 output (key `a92d9cabba3b68fe`) has records and metadata only; the resume store, which held the replies, was deleted on publish (ADR-0054 Amendment 2). So a raw-reply reference has to be made again (decision 2).

## Decision

### 1. The rule

Keeping the model loaded is adopted **only if**, for **every one of the 23 Day 4 windows**, the reply is byte-identical to the reference (decision 2) **in each of three repeats** made within **one loaded session**:

- repeat 1: windows in order (0 to 22);
- repeat 2: windows in order again;
- repeat 3: windows in reverse order (22 to 0).

"Byte-identical" is defined in decision 3. **Any difference in any window, in any repeat, keeps reload per call** (`keep_alive` 0). There is no tolerance and no partial adoption (for example "keep loaded, but only for some windows").

After a failure, keeping the model loaded can come back only with a **quality check on a fresh lecture** (a lecture that is neither Day 4 nor the held-out one, with its own gold, under a new ADR), never by re-running this test until it passes.

Speed is not part of the rule. It is measured (decision 5) and reported, but a pass is adopted however small the speed-up is, and a failure is not overridden by a large one.

### 2. The reference: run 0

- **Run 0** is a fresh reload-per-call run (`keep_alive` 0, the frozen configuration unchanged) over the 23 Day 4 windows in order, made **in the same session** as the repeats: the same Ollama process (the app not restarted or updated in between), the same day, run immediately before repeat 1.
- Run 0 captures each window's raw reply (decision 3).
- **Run 0 must reproduce v2.** Its parsed records (decision 3) must be byte-identical to the 23 records in the published v2 `extraction.json` (key `a92d9cabba3b68fe`), compared the same way as ADR-0055 evidence (c) (`compare_day4_v2.py`: canonical JSON, records by window index). Each of the 23 windows must also be valid on attempt 1, as in v2.
- **If run 0 does not match v2, the session stops** and no repeat is run. That is a reproducibility problem of reload per call (or of the environment), not a keep-alive result, and it is reported as such. No adoption decision is taken from that session.
- Run 0 is the reference for all three repeats. The repeats are not compared with v2 directly, but because run 0 = v2, a pass also means every repeat's records equal v2.

### 3. What "byte-identical" compares

Two comparisons per window, and **both** must match:

1. **The raw reply:** the `message.content` string of Ollama's `/api/chat` reply as received (the decoded JSON string, before any parsing or clean-up), compared as UTF-8 bytes with run 0's. Only the extraction call (attempt 1) is compared; see decision 4 for retries.
2. **The parsed record:** the window's record after the stage's own reply handling (`parse_reply` with `drop_self=True`: dangling relations, then self-relations dropped, then validated), as canonical JSON (`sort_keys`, no spaces, `ensure_ascii` false), compared with run 0's. A window that is valid in run 0 and invalid in a repeat is a difference.

The evidence records, per window and repeat, the sha256 of the raw reply, the sha256 of the canonical record, the validity category, and the two equalities. Ollama's timing fields are not compared (they differ on every call).

### 4. How the runs are done

- **Code path: a dedicated evaluation command, not the production stage.** Proposed: `insightex extract-eval keepalive` in `backend/src/insightex/extract/` (beside the harness, as an evaluation entry point; not in `tools/`, which may not import `backend/`). It builds each request with the stage's own request builder (`calls.py` and the stage's call options), so the requests are the stage's requests with only `keep_alive` changed; a unit test checks that. The production stage is not used because:
  - it unloads the model in a `finally` block at the end of every run, so the model could not stay loaded across three repeats;
  - a run under a different `keep_alive` has a different fingerprint, so publishing would replace Day 4's v2 stage folder (`stages/extract/a92d9cabba3b68fe/`) with a new key;
  - it publishes no raw replies, and decision 3 needs them.
  The command reads the Day 4 windows from the index stage's `windows.json` at the manifest's current index key, **read-only**, and writes nothing into any workspace (no `stages/`, no `.resume/`, no manifest).
- **The session, in order:**
  1. `dev_run.sh` (API and worker) is stopped, and no browser tab is open on Insightex. The lecture page's warm-up loads `qwen3.5:latest` (M6), which is what was found resident after the Day 4 rerun; nothing else may load a model during the session.
  2. `check_ollama_frozen.py` prints `OK:`.
  3. The command takes the GPU lease for the whole session, so no worker stage can start, unloads every resident model through the lease, and checks that `/api/ps` is empty.
  4. VRAM baseline: nvidia-smi used memory with no model loaded.
  5. The run-start self-test (ADR-0049 Amendment 2), once, with the frozen settings. It is not repeated before the repeats: it runs at `num_ctx` 2048, which would make Ollama load the model again at a different context size inside the session (**unverified**, so the load check below would catch it anyway).
  6. Run 0 (decision 2), `keep_alive` 0. Then a check that `/api/ps` is empty.
  7. Repeats 1, 2 and 3 with `keep_alive` **600** (seconds; ADR-0002's "10m"). The gap between calls is seconds, so 600 never expires during the session; each request resets it.
  8. At the end, the command unloads the model (`keep_alive` 0, then polling `/api/ps` until it is gone), releases the lease, and records the final VRAM.
- **Checks that the model really stayed loaded**, before each repeat and after the last one:
  - `/api/ps` lists exactly one model, `gemma4:e4b`, with the frozen digest, `context_length` 8192, and an `expires_at` in the future;
  - idle VRAM above baseline is at least 90% of the idle figure measured right after repeat 1 (a sign the weights are still on the GPU). `ollama ps`'s `size_vram` is not used as evidence of GPU residency for Gemma (ADR-0049 decision 6: it under-reports Gemma);
  - **load check per call:** Ollama's `load_duration` for every call is recorded. In run 0 every call must show a load (`load_duration` ≥ 1 s; measured loads are about 6 s). In the repeats, only the first call of repeat 1 may show one; every other call must have `load_duration` < 1 s.
- **A failed check voids the session.** If any residency or load check fails, or another model appears in `/api/ps`, the session stops and is recorded as **void**: not a pass and not a failure of the rule. A void session may be run again from step 1, run 0 included; every void session stays in the evidence.
- **Retries.** Only attempt 1 is sent. Run 0 must be valid on attempt 1 for every window (decision 2). In a repeat, an invalid attempt 1 is already a difference, so the rule fails without needing the retry.
- **Who runs it:** Bilal, or me only when he says so, after this ADR is accepted and the command and its tests are reviewed.

### 5. What is measured and recorded

Per call: wall time as seen by the client, `load_duration`, `prompt_eval_count`, `eval_count`, `eval_duration` (tokens per second = `eval_count / eval_duration`, decode speed only). Per run (run 0 and each repeat): total wall time, mean and maximum wall time per window, tokens per second, VRAM baseline (the session baseline from step 4), VRAM peak above baseline (nvidia-smi polled during the run), and idle VRAM above baseline at the end of the run. Plus the Ollama version and model digest served, the self-test result, the residency and load checks, and the equalities of decision 3.

**Counts, timings, hashes, statuses and equality only.** No labels, relation text, reply text or transcript text goes into an evidence file or is printed by the command. A VRAM peak above 5000 MiB (ADR-0054 Amendment 2's `min_free_vram_mib`) is reported, not a gate.

### 6. What adoption changes, if the rule passes

Adoption is a new decision taken by Bilal on the evidence (this ADR accepted as passed, or a short follow-up note in it), then:

- **`extract.stage.keep_alive` becomes 600**, the value tested. The stage keeps unloading the model at the end of every run (GPU contract), so 600 only matters between calls within one run.
- **The fingerprint changes** (`keep_alive` is in it), so every lecture's extraction becomes `outdated` and a re-add re-extracts it: Day 4, `yt-B7TQYJLfYZQ`, and any other extracted lecture. The held-out lecture stays held (its `extract` is skipped) and is not re-added.
- **ADR-0054 decision 2 is superseded** for the stage: the override of ADR-0002 becomes keeping the model loaded within a run. The harness keeps reload per call (ADR-0049 decision 6 is unchanged for evaluation).
- **ADR-0054 decision 5's soundness argument is revisited.** A resume after a crash starts a new session (a fresh load), while the stored replies came from a loaded session. Run 0 = repeats on Day 4 shows those are the same for these 23 windows; that is the argument, on Day 4 evidence only. The revisit states this limit.
- **The byte-identical request test is updated** as ADR-0054 already says: the stage's request is compared with the harness's with `keep_alive` held equal (every other field must match), and a separate assertion checks that the stage sends `extract.stage.keep_alive`.

If the rule fails, nothing changes: `keep_alive` stays 0, no lecture is re-extracted, and this ADR records the failure (which window, which repeat, which comparison, counts only).

### 7. Where the run files go

- **Committed evidence:** `docs/evidence/m7/session3/keepalive/<UTC stamp>/`: `session.json` (settings, served version and digest, checks, per-run timings and VRAM, the outcome: pass, fail or void) and `windows.json` (per window and run: sha256 of the reply and of the record, category, equalities, `load_duration`, wall time). One folder per session, void sessions included.
- **Raw replies** (needed to compare, but text): kept outside the repo, in `$INSIGHTEX_DATA/m7_private/keepalive/<UTC stamp>/` (not in any workspace), so they can be re-checked against the committed hashes. They are never committed.
- **Not used:** `yt-5vqk6HnITko`. The command refuses any lecture other than Day 4 (`sha256-de27cb67c2acbedebd0c2c7416932b8a`).

## Alternatives considered

- **Use the production stage with stored replies ignored** (the plan's first idea). Rejected for the three reasons in decision 4: it unloads at the end of every run, it would replace Day 4's published v2 folder, and it keeps no raw replies.
- **Compare the repeats with v2 only, with no run 0.** Rejected: v2 kept no raw replies, so only records could be compared, and a reproducibility problem in the environment could not be told apart from a keep-alive effect.
- **Compare parsed records only.** Rejected: a reply can change without changing the record (for example a dropped relation), and that change is the session-state effect this test is looking for.
- **Fewer repeats, or no reverse order.** Rejected: the synthetic evidence showed a reply changing on a repeat in the same session; reverse order puts different previous calls before each window, which is what a prompt-cache effect would depend on.
- **Keep the model loaded with a tolerance** (for example, adopt if records match on most windows). Rejected: the stage's resume and the request test rest on exact reproducibility; anything weaker needs a quality check on a fresh lecture.

## Consequences

- One Day 4 session of about 23 × 9 s (run 0) plus 3 × 23 × about 3 s (repeats), roughly 7 minutes of GPU time (**estimate**, the repeat time per window unmeasured).
- New code (after acceptance): the `keepalive` command with unit tests on a fake client (window order, reverse order, both comparisons, the load and residency checks voiding a session, refusal of other lectures, nothing written into a workspace, request identity with the stage except `keep_alive`).
- If it passes: about 6–7 s less per window (**unverified** until measured) and a re-extraction of every extracted lecture. If it fails: reload per call stays, and the only way back is a fresh-lecture quality check.

## Evidence

None yet: no code written, nothing run. To be added after the session: the committed folder of decision 7 and the outcome.

## Gate / revisit when

- **Gate:** decision 1's rule, on one valid (not void) session whose run 0 matches v2.
- **Revisit** if Ollama, the Gemma digest or the frozen configuration changes (the result holds only for Ollama 0.40.2, digest `dc35e8d9…0c9c`, and the frozen prompt v2), or when a fresh lecture with gold is available (the only route back after a failure).
