# ADR-0056: M7 Session 3 decision (a): keep Gemma loaded between extract-stage calls, only if Day 4 and the ADR-0049 case stay byte-identical

Status: Accepted
Date decided: 2026-11-22
Date recorded: 2026-11-22
Module: M7

Decision (a) of M7 Session 3 (handoff 5, item 1). It sets, before any run, the test that decides whether the production `extract` stage may keep the model loaded between its single-window calls, instead of reloading it for every call (ADR-0054 decision 2). It uses the Day 4 lecture and the synthetic ADR-0049 case only; the held-out lecture `yt-5vqk6HnITko` is not used. Accepted by Bilal on 2026-11-22 after review: the synthetic counterexample added to the rule, the void-session rules, and committed raw replies.

## Context

- **Reload per call is the frozen setting.** `extract.stage.keep_alive` is 0 (ADR-0054 decision 2), as in every M7 run (ADR-0049 decision 6). It is part of the stage fingerprint.
- **It is the main cost.** About 6.3–7.1 s of every ~9 s window is the model load (M7 report section 5). Day 4 at stage v2 took 179.6 s for 23 windows; `yt-B7TQYJLfYZQ` took 233.1 s for 28 (both measured, Session 3).
- **Why reload per call was chosen: an observed counterexample.** ADR-0049 ("Gemma's session-state dependence", decision 6; measurements in `docs/evidence/m7/session2b_vram_numctx.md`, section "Determinism and replay at temperature 0") found that on synthetic input Gemma's replies at temperature 0 depended on session state. With Gemma as shipped (draft model on, as the stage runs it), the k = 3 case (windows 18, 20, 21 of `docs/measurements/m7/synthetic/day4_shape.json`) sent twice in a row in one loaded session gave `e2a7020f…` and then `214e43e6…`, and a fresh load reproduced `e2a7020f…` (`docs/measurements/m7/synthetic/determinism_gemma4_e4b.json`; repeated exactly in `determinism_gemma4_e4b_run2.json`). Under reload per call both cases were byte-identical over three calls (`reload_determinism_gemma4_e4b.json`: k = 1 `1d414909…`, k = 3 `e2a7020f…`). The likely cause, prompt-cache reuse between calls, is **unverified**. So the prior evidence predicts that this test may well fail; it is run because the speed-up is large and that evidence is synthetic, not Day 4.
- **What depends on reproducibility.** ADR-0054 decision 5 reuses a stored reply after a crash because "a repeated request returns a byte-identical reply". The request-identity test compares the stage's request with the harness's with `keep_alive` equal (both 0).
- **v2 published no raw replies.** The Day 4 stage v2 output (key `a92d9cabba3b68fe`) has records and metadata only; the resume store, which held the replies, was deleted on publish (ADR-0054 Amendment 2). So a raw-reply reference has to be made again (decision 2).
- **The ADR-0049 case can be rebuilt exactly from the repo** (checked 2026-11-22, no model run). The messages built today from `placeholder_prompt_retry.txt` are byte-identical to those built on 18 Oct 2026 (code at `adad53c`) from `placeholder_prompt.txt` (sha256 `e74bdfaa…`, the hash in the result file). The JSON Schema `format` is not: ADR-0049 Amendment 1 (`cf00174`, 18 Oct 2026 04:37) added `maxItems: 10` to concepts and relations, after all the Gemma determinism runs (the determinism and reload-determinism files were committed before 04:00 that day). The case is therefore frozen as the exact request bodies of `determinism.py` built with the `adad53c` code (decision 4).

## Decision

### 1. The rule

Keeping the model loaded is adopted **only if both** of these hold, in **one loaded session**:

- **Day 4:** for every one of the 23 windows, the reply is byte-identical to the Day 4 reference (decision 2) in each of three repeats: repeat 1 in window order (0 to 22), repeat 2 in window order again, repeat 3 in reverse order (22 to 0);
- **The ADR-0049 case:** for both of its requests (k = 1: window 18; k = 3: windows 18, 20, 21; draft model on, as shipped), the reply is byte-identical to the synthetic reference (decision 2) in each of three repeats: repeats 1 and 2 in order (k = 1, then k = 3), repeat 3 reversed (k = 3, then k = 1). Repeat 3 therefore sends the k = 3 request straight after repeat 2's k = 3 request, which is the same-session pair in which ADR-0049 saw the reply change.

"Byte-identical" is defined in decision 3. **Any difference in either part, in any window, case or repeat, keeps reload per call** (`keep_alive` 0). There is no tolerance and no partial adoption (for example "keep loaded, but only for some windows").

**Why the synthetic case is part of the rule.** A Day 4 pass cannot outweigh an observed failure elsewhere: ADR-0049 saw Gemma's reply change within a loaded session on that input. If keeping the model loaded were adopted while that case still changes, the stage's resume store (ADR-0054 decision 5) would be unsound for such inputs: a stored reply would no longer be what a new call returns. So the counterexample must also stop reproducing, under the same conditions as Day 4, before the setting can change.

After a failure, keeping the model loaded can come back only with a **quality check on a fresh lecture** (a lecture that is neither Day 4 nor the held-out one, with its own gold, under a new ADR), never by re-running this test until it passes.

Speed is not part of the rule. It is measured (decision 5) and reported, but a pass is adopted however small the speed-up is, and a failure is not overridden by a large one.

### 2. The references

- **Day 4: run 0.** A fresh reload-per-call run (`keep_alive` 0, the frozen configuration unchanged) over the 23 Day 4 windows in order, made **in the same session** as the repeats: the same Ollama process (the app not restarted or updated in between), the same sitting, immediately before the synthetic reference. Run 0 captures each window's raw reply (decision 3).
  - **Run 0 must reproduce v2.** Its parsed records (decision 3) must be byte-identical to the 23 records in the published v2 `extraction.json` (key `a92d9cabba3b68fe`), compared the same way as ADR-0055 evidence (c) (`compare_day4_v2.py`: canonical JSON, records by window index), and each of the 23 windows must be valid on attempt 1, as in v2.
- **The ADR-0049 case: its reference run.** Both requests sent once each with `keep_alive` 0 (a fresh load for each), after run 0. Each reply must reproduce ADR-0049's fresh-load hash: k = 1 `1d4149094132414971d8e5cb17413546784d68741a414ec6176cf1336829e31e`, k = 3 `e2a7020f993e0b54ab98e5c081d354ada1b8bde8eeec66488b042fe33747bedc`.
- **If either reference does not reproduce, the session stops** and no repeat is run. That is a reproducibility problem of reload per call (or of the environment), not a keep-alive result, and it is reported as such. No adoption decision is taken from that session.
- The references are what every repeat is compared with. Because run 0 = v2, a pass also means every Day 4 repeat's records equal v2.

### 3. What "byte-identical" compares

Two comparisons per window or case, and **both** must match:

1. **The raw reply:** the `message.content` string of Ollama's `/api/chat` reply as received (the decoded JSON string, before any parsing or clean-up), compared as UTF-8 bytes with the reference's. Only attempt 1 is sent (decision 4).
2. **The parsed result:**
   - Day 4: the window's record after the stage's own reply handling (the post-call overflow check, then `parse_reply` with `drop_self=True`: dangling relations, then self-relations dropped, then validated), as canonical JSON (`sort_keys`, no spaces, `ensure_ascii` false). A window that is valid in run 0 and invalid in a repeat is a difference.
   - The ADR-0049 case: the reply parsed as JSON and written as canonical JSON in the same way (its placeholder prompt and pre-Amendment-1 `format` are not the frozen configuration, so the stage's validation does not apply). A reply that is not JSON is a difference.

The evidence records, per window or case and run, the sha256 of the raw reply and of the canonical parsed result, the Day 4 validity category, and the two equalities. Ollama's timing fields are not compared (they differ on every call).

### 4. How the runs are done

- **Code path: a dedicated evaluation command, `insightex extract-eval keepalive`,** in `backend/src/insightex/extract/` (beside the harness, as an evaluation entry point; not in `tools/`, which may not import `backend/`).
  - Day 4 requests are built with the stage's own request builder, so they are the stage's requests with only `keep_alive` changed; a unit test checks that.
  - The ADR-0049 case is sent from a committed, frozen file of its two exact request bodies (messages, `format`, options, as `determinism.py` built them with the `adad53c` code: no `truncate` field, `num_predict` 1024 × k), checked by sha256 before use; only `keep_alive` is set by the session.
  - The production stage is not used: it unloads the model in a `finally` block at the end of every run, so the model could not stay loaded across the repeats; a run under a different `keep_alive` has a different fingerprint, so publishing would replace Day 4's v2 stage folder; and it publishes no raw replies.
  - The command reads the Day 4 windows from the index stage's `windows.json` at the manifest's current index key and the v2 records from `stages/extract/a92d9cabba3b68fe/`, **read-only**, and writes nothing into any workspace (no `stages/`, no `.resume/`, no manifest).
- **The session, in order:**
  1. `dev_run.sh` (API and worker) is stopped, and no browser tab is open on Insightex. The lecture page's warm-up loads `qwen3.5:latest` (M6), which is what was found resident after the Day 4 rerun; nothing else may load a model during the session.
  2. `check_ollama_frozen.py` prints `OK:`; the command also checks the served Ollama version and Gemma digest against the frozen values.
  3. The command takes the GPU lease for the whole session, so no worker stage can start, unloads every resident model, and checks that `/api/ps` is empty.
  4. VRAM baseline: nvidia-smi used memory with no model loaded.
  5. The run-start self-test (ADR-0049 Amendment 2), once, with the frozen settings. It is not repeated: it runs at `num_ctx` 2048, which would probably make Ollama load the model again inside the session (**unverified**; the load check below would catch it).
  6. Day 4 run 0, then the ADR-0049 reference run, both with `keep_alive` 0. Then a check that `/api/ps` is empty.
  7. In one loaded session with `keep_alive` **600** (seconds; ADR-0002's "10m"; each request resets it, and the gaps between calls are seconds): Day 4 repeats 1, 2 and 3, then the ADR-0049 case's repeats 1, 2 and 3. The model is not unloaded in between.
  8. At the end, the command unloads the model (`keep_alive` 0, then polling `/api/ps` until it is gone), releases the lease, and records the final VRAM.
- **Checks that the model really stayed loaded**, before each repeat after the first and after the last one:
  - `/api/ps` lists exactly one model, `gemma4:e4b`, with the frozen digest, `context_length` 8192, and an `expires_at` in the future;
  - idle VRAM above baseline is at least 90% of the idle figure measured right after Day 4 repeat 1 (a sign the weights are still on the GPU). `ollama ps`'s `size_vram` is not used as evidence of GPU residency for Gemma (ADR-0049 decision 6: it under-reports Gemma);
  - **load check per call:** Ollama's `load_duration` for every call is recorded. In run 0 and the ADR-0049 reference run, every call must show a load (`load_duration` ≥ 1 s; measured loads are about 6 s). In the repeats, only the first call of Day 4 repeat 1 may show one; every other call must have `load_duration` < 1 s.
- **Void sessions.**
  - If any residency or load check fails, another model appears in `/api/ps`, or Ollama fails (unreachable, an HTTP error), the session stops and is **void**.
  - **Any reply or parsed-result difference observed in any session, void or not, counts as a failure of the rule.** Reason: reload per call is deterministic (ADR-0049 decision 6), so a reload cannot create a difference against the reference; a difference can only come from the loaded state. So a void session that saw a difference is recorded as a failure, not as void.
  - A void session with **no** differences is not a result either way. Before any redo, its cause is recorded in its evidence (the command records the failed check and its values when it stops; Bilal may add a note). It may then be redone from step 1, run 0 included. There is no limit on redos in that case, and every void session is kept in the evidence.
- **Retries.** Only attempt 1 is sent. Run 0 must be valid on attempt 1 for every window (decision 2). In a repeat, an invalid or truncated attempt 1 is already a difference, so the rule fails without needing the retry.
- **Who runs it:** Bilal, or me only when he says so, after the command and its tests are reviewed. For the session, I may stop and restart `dev_run.sh` myself.

### 5. What is measured and recorded

Per call: wall time as seen by the client, `load_duration`, `prompt_eval_count`, `eval_count`, `eval_duration` (tokens per second = `eval_count / eval_duration`, decode speed only). Per run (run 0, the ADR-0049 reference run, and each repeat): total wall time, mean and maximum wall time per call, tokens per second, VRAM baseline (the session baseline from step 4), VRAM peak above baseline (nvidia-smi polled during the run), and idle VRAM above baseline at the end of the run. Plus the Ollama version and model digest served, the self-test result, the residency and load checks, and the equalities of decision 3.

`session.json` and `windows.json` hold **counts, timings, hashes, statuses and equality only**; the command prints nothing else. The raw replies are in `replies.jsonl` (decision 7). A VRAM peak above 5000 MiB (ADR-0054 Amendment 2's `min_free_vram_mib`) is reported, not a gate.

### 6. What adoption changes, if the rule passes

Adoption is a new decision taken by Bilal on the evidence (recorded in this ADR's Evidence and a follow-up ADR), then:

- **`extract.stage.keep_alive` becomes 600**, the value tested. The stage keeps unloading the model at the end of every run (GPU contract), so 600 only matters between calls within one run.
- **The fingerprint changes** (`keep_alive` is in it), so every lecture's extraction becomes `outdated` and a re-add re-extracts it: Day 4, `yt-B7TQYJLfYZQ`, and any other extracted lecture. The held-out lecture stays held (its `extract` is skipped) and is not re-added.
- **ADR-0054 decision 2 is superseded** for the stage: the override of ADR-0002 becomes keeping the model loaded within a run. The harness keeps reload per call (ADR-0049 decision 6 is unchanged for evaluation).
- **ADR-0054 decision 5's soundness argument is revisited.** A resume after a crash starts a new session (a fresh load), while the stored replies came from a loaded session. The references = repeats on Day 4 and on the ADR-0049 case show those are the same for these inputs; that is the argument, on this evidence only. The revisit states this limit.
- **The byte-identical request test is updated** as ADR-0054 already says: the stage's request is compared with the harness's with `keep_alive` held equal (every other field must match), and a separate assertion checks that the stage sends `extract.stage.keep_alive`.

If the rule fails, nothing changes: `keep_alive` stays 0, no lecture is re-extracted, and this ADR records the failure (which part, window or case, repeat, and comparison; counts only).

### 7. Where the run files go

- **Committed evidence, one folder per session (void sessions included):** `docs/evidence/m7/session3/keepalive/<UTC stamp>/`:
  - `session.json`: settings, served version and digest, the self-test, the checks, per-run timings and VRAM, a void session's cause, and the outcome (pass, fail, void, or stopped because a reference did not reproduce);
  - `windows.json`: per window or case and run, the sha256 of the reply and of the parsed result, the category, the equalities, `load_duration` and wall time;
  - `replies.jsonl`: the raw replies, one line per call (run, window or case, attempt, content), like the M7 `calls.jsonl` files. Only Day 4 and the ADR-0049 case, never any other lecture.
- **The frozen ADR-0049 case:** `docs/evidence/m7/session3/keepalive/adr0049_case.json` (the two request bodies and the reference hashes), with the script that built it from the `adad53c` code in `docs/evidence/m7/session3/scripts/`.
- **Not used:** `yt-5vqk6HnITko`. The command refuses any lecture other than Day 4 (`sha256-de27cb67c2acbedebd0c2c7416932b8a`) and any synthetic case file other than the frozen one.

## Alternatives considered

- **Use the production stage with stored replies ignored** (the plan's first idea). Rejected for the reasons in decision 4: it unloads at the end of every run, it would replace Day 4's published v2 folder, and it keeps no raw replies.
- **Test Day 4 only.** Rejected at review: a Day 4 pass cannot outweigh the observed ADR-0049 failure, and adoption would make the resume store unsound for such inputs (decision 1).
- **Rebuild the ADR-0049 case with today's `format`.** Rejected: that is not the request ADR-0049 sent (it lacks the pre-Amendment-1 schema), so it would not test the observed counterexample.
- **Compare the Day 4 repeats with v2 only, with no run 0.** Rejected: v2 kept no raw replies, so only records could be compared, and a reproducibility problem in the environment could not be told apart from a keep-alive effect.
- **Compare parsed results only.** Rejected: a reply can change without changing the record (for example a dropped relation), and that change is the session-state effect this test is looking for.
- **Fewer repeats, or no reverse order.** Rejected: the synthetic evidence showed a reply changing on a repeat in the same session; reverse order puts different previous calls before each request, which is what a prompt-cache effect would depend on.
- **Treat a void session's differences as void too.** Rejected: under reload per call a reload cannot create a difference, so any difference comes from the loaded state.
- **Keep raw replies outside the repo.** Rejected at review: they are committed like the M7 `calls.jsonl` files, Day 4 and the synthetic case only.

## Consequences

- One session of about 23 × 9 s (run 0) plus 2 × 7 s (the ADR-0049 reference) plus 3 × 23 × about 3 s and 3 × 2 synthetic calls (the repeats), roughly 8 minutes of GPU time (**estimate**; the repeat time per call is unmeasured).
- New code: the `keepalive` command with unit tests on a fake client (the comparisons, the void checks, a difference in a void session counting as a failure, the refusal of any lecture but Day 4 and of any synthetic case but the frozen one, nothing written into a workspace, the Day 4 request equal to the stage's except `keep_alive`).
- If it passes: about 6–7 s less per window (**unverified** until measured) and a re-extraction of every extracted lecture. If it fails: reload per call stays, and the only way back is a fresh-lecture quality check.

## Evidence

- The ADR-0049 counterexample: `docs/measurements/m7/synthetic/determinism_gemma4_e4b.json` and `_run2.json`, `reload_determinism_gemma4_e4b.json`; `docs/evidence/m7/session2b_vram_numctx.md`, section "Determinism and replay at temperature 0".
- The rebuild check (2026-11-22): messages equal between `adad53c` and today's builders; `format` differs only by the two `maxItems: 10` of ADR-0049 Amendment 1.
- The session: to be added (decision 7).

## Gate / revisit when

- **Gate:** decision 1's rule, on one session that is not void and whose two references reproduced.
- **Revisit** if Ollama, the Gemma digest or the frozen configuration changes (the result holds only for Ollama 0.40.2, digest `dc35e8d9…0c9c`, and the frozen prompt v2), or when a fresh lecture with gold is available (the only route back after a failure).
