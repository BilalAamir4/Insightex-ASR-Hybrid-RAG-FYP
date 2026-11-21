# ADR-0055: M7 Session 3: the production extract stage drops self-pointing relations instead of failing the window

Status: Proposed
Date decided: not decided (draft for review, 2026-11-21)
Date recorded: 2026-11-21
Module: M7

## Context

Step 3 of M7 Session 3 is decision (b) of the approved plan: what the production `extract` stage (ADR-0054) does with a relation whose head and tail are the same concept.

Today the stage uses the M7 rule unchanged (ADR-0048 section 7, ADR-0054 decision 4). `check_labels` in `extract/extraction_schema.py` rejects a self-relation as a window error. The window is retried once with the error in the frozen retry template, and it is `failed` if the retry is still invalid. The C4 context arm was rejected on validity for exactly this case: on Day 4 window 6 both attempts had a relation with head = tail (ADR-0053). One self-relation therefore costs the whole window's concepts, even though dropping the relation would leave a valid record. Dangling relations are already handled that way: they are dropped and counted (`drop_dangling`, ADR-0048 section 7).

**What the check is, read from the code (2026-11-21).** This differs from the review instruction's wording ("the validator's own name normalisation over labels and aliases"), so it is a review point below.
- `check_labels` (lines 159–181) first requires each relation end to be **exactly** the `label` of a concept in the window (`r[end] in label_set`, a plain string set). Otherwise the error is "is not the label of a concept in this window", not a self-relation error.
- Only then does it test `r["head"] == r["tail"]`, a plain string comparison. There is no `normalise()` call and no alias lookup in that test.
- In the stage, `drop_dangling` (in `extract/calls.py`) runs before validation and removes every relation whose head or tail is not an exact concept label. A relation that names an alias at either end never reaches the self-relation check; it is dropped and counted as dangling.
- Within one window the validator also requires that no two names (labels and aliases, after `normalise()`) belong to two different concepts. Two different label strings can therefore never be the same concept in a valid record. Each concept has exactly one label.
- So after `drop_dangling`, "head and tail resolve to the same concept" holds exactly when `head == tail` as strings. Normalising labels and aliases would find no other cases in a record that passes the rest of the validator. In a record that fails the name-uniqueness rule, the window fails on that rule anyway.

## Decision

1. **The rule (production stage only).** After `drop_dangling` and before validation, the stage removes every relation whose `head` equals its `tail` (exact string comparison, the comparison `check_labels` makes). It counts them as `dropped_self_relations`. The rest of the record is then validated as before; a record that is invalid for any other reason still gets its retry and can still fail.
   - "Same concept" is defined by the check this rule replaces: exact equality of two strings that are both concept labels of the window. It is not a new normalisation (see Context: after `drop_dangling` it is the only way head and tail can be the same concept).
   - The direction of `contrasts_with` (symmetric, `relation_key`) does not matter: a self-relation reads the same both ways, and it is dropped for every relation type.
   - The validator (`extraction_schema.py`, both byte-identical copies) is **not changed**. It still rejects self-relations, so gold files and harness runs are judged by the M7 rule. The stage never sends a self-relation to it.
   - Implementation: a stage-only option on the shared reply parser (for example `parse_reply(..., drop_self=True)`, default false), used only by `extract/stage.py`.
2. **The harness keeps the M7 rule.** `extract-eval` does not pass the option, its records and errors are unchanged, and `HARNESS_VERSION` stays **8**. Every committed M7 run stays reproducible and its reply-cache keys stay valid.
3. **Stage version 1 → 2.** `ExtractStage.version` becomes `"2"`, so every extract key changes and every extracted lecture is re-extracted on its next job (a re-add is no longer a no-op). The producer name in `extraction.json` becomes `extract stage v2 (gemma4:e4b)` (the document header changes; window records are compared without it). The fingerprint fields are unchanged; the version alone changes the key through `stage_key`.
4. **Where the count appears.**
   - `extract.json`:
     - `totals.dropped_self_relations` (all windows);
     - per window, `dropped_self_relations`, next to the existing `dropped_relations` (dangling), which keeps its meaning.
   - The manifest extra: `dropped_self_relations` next to `dropped_relations`.
   - No warning. A dropped self-relation is not a failed window, and the user-facing warnings are unchanged.
   - A window whose record is valid only because self-relations were dropped is `ok` (or `ok_after_retry` if its other errors needed the retry).
5. **Requests do not change.**
   - Messages, `format`, options and `keep_alive` are built as before, so the byte-identical request test (ADR-0054 decision 1, `test_extract_request_identity.py`) is unaffected.
   - The only change in what is sent: a first attempt that is valid after dropping no longer triggers the retry, so that window's second request is never sent. The test compares first-attempt requests and still holds.
   - Request building is unchanged; it is the decision to retry that changes.
6. **No quality claim.** This ADR makes no claim that the stage's concepts or relations get better or worse. It keeps windows that would otherwise be lost. Nothing is counted, read or rerun in the held-out lecture's run files or workspace (`yt-5vqk6HnITko`, used up; held since 21 Nov 2026).

## Alternatives considered

- **Keep failing the window (status quo).** Rejected: one self-relation, which `drop_dangling`-style handling already treats as droppable for dangling ends, discards every concept of the window. In the C4 context arm this was enough to reject the arm.
- **Change the validator (both copies) to drop instead of reject.** Rejected: the validator judges gold files and every M7 run; changing it would change the M7 rule after the fact and the evidence would no longer be reproducible under the same rule.
- **Drop self-relations in the harness too, as a harness 9.** Rejected: M7's comparisons are decided and the held-out lecture is used up; a harness change cannot be evaluated and would only break reproducibility.
- **Normalise head and tail (and aliases) before comparing.** Not needed: after `drop_dangling` both ends are exact labels, and labels of different concepts never share a normalised name in a record that passes the rest of the validator, so normalisation finds no extra cases. It would also be a different rule from the check it replaces.
- **Turn a self-relation into a warning.** Rejected: it is model noise inside one record, like a dangling relation, not something the user can act on.

## Consequences

- **Code (after acceptance, not before):**
  - `extract/calls.py`: the stage-only drop and its count.
  - `extract/stage.py`: version `"2"`, the count in `extract.json` and the manifest extra.
  - The tests below.
  - `docs/contracts/api.md`: one line, if the manifest extra is mentioned there.
  - Harness and validator untouched.
- **Re-extraction.**
  - Day 4 (`sha256-de27cb67c2acbedebd0c2c7416932b8a`) is re-extracted on its next job. On the normal path, the runner removes the superseded v1 key directory (`stages/extract/ca8f42ef0c179994/`) when it publishes v2 (`jobs/workspace.py`, superseded key). That is the system's own clean-up, not a manual delete. The step 2 evidence is kept in `docs/evidence/m7/session3/m7_verify_20261121T145444Z.json` (counts only). Whether to copy the v1 `extract.json`/`extraction.json` into the evidence folder first is a review point.
  - The held-out lecture is held, so its jobs skip `extract`; it is not touched.
- **Tests (fake client, synthetic records):**
  - a self-relation on the same label is dropped and counted, and the window is `ok` with no retry;
  - a relation from a label to an alias of the same concept is dropped as dangling (counted in `dropped_relations`, not in `dropped_self_relations`), and the window is `ok`;
  - the same for alias to alias;
  - `contrasts_with` self-relations are dropped, as are those of the three directed types;
  - a record with a self-relation and another error is retried and can fail;
  - the harness still rejects a self-relation (unchanged harness test, `HARNESS_VERSION` 8);
  - the version bump changes the key and a re-add re-extracts;
  - `extract.json` totals, the per-window count and the manifest extra;
  - the byte-identical request test still passes.

## Evidence

All decided before any run or count.

(a) **Unit tests on synthetic records**, as listed under Consequences: same label; label vs alias; alias vs alias; and `contrasts_with` (both directions read the same) plus each directed type. They show the rule and its boundary with the dangling rule. No lecture text.

(b) **Count of self-relations in the committed Day 4 run files only.**
- **Files.** Every arm under `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/`: `C1/C1-gemma4-e4b`, `C1/C1-qwen3.5`, `C2/C2-original`, `C2/C2-english`, `C3/C3-single`, `C3/C3-batch`, `C4/C4-window`, `C4/C4-previous` (including window 6). `C4-window` is a byte copy of `C1-gemma4-e4b` (`reused_from.json`), so it is reported as identical, not counted twice. `prompt_iteration/` is not part of C1–C4 and is not counted.
- **Method**, written down now:
  1. Read each arm's `calls.jsonl`.
  2. Keep extraction calls only (`kind`); translation calls have no relations.
  3. For each call with a non-null `content` that parses as JSON with a `windows` list, and for each window record in it, look at each relation. Count it as a self-relation when `head` and `tail` are both strings, equal, and equal to the `label` of a concept in the same record. Separately count equal head/tail values that are not a label of that record; those would be dropped as dangling first.
  4. Output per arm: totals, and per call `(window_index, attempt, count)`. Also, per arm, the windows whose attempt was rejected *only* because of self-relations, i.e. the record has no other validation error once its self-relations and dangling relations are removed. This is checked by running the unchanged validator on a copy without them.
  5. No labels, relation text or reply text is printed or written; only counts, window indices and attempt numbers.
- **Written by** a script under `docs/evidence/m7/session3/scripts/`.
- **Results** in `docs/evidence/m7/session3/self_relations_day4.json`.

(c) **A Day 4 rerun of the stage at version 2**, after the code and tests, with Ollama checked by `check_ollama_frozen.py` first.
- **Expected outcome, stated in advance:**
  - A C1 window changes only if C1's first attempt for it was rejected only because of self-relations (found in (b)). In that case v2 keeps the first attempt minus its self-relations, where C1 used the second attempt or failed the window.
  - The records for the 20 C1 target windows stay byte-identical to `C1/C1-gemma4-e4b/extraction.json` otherwise. No valid C1 record contains a self-relation, because the validator would have rejected it.
  - Windows 0, 3 and 5 (not C1 targets) are reported in the same way against the step 2 v1 run, whose counts-only record is in the m7_verify results file.
- **Reported:** every window that changes, with its reason (attempt used before and after, count of dropped self-relations). Any change without such a reason is a failure of this expectation and stops the step for review.
- **Counts only**, like m7_verify; no labels or relation text.
- **Who runs it:** Bilal, or me only when he says so.

## Review points (for Bilal, before acceptance)

1. **Normalisation wording.** The review instruction asks for "the validator's own name normalisation over labels and aliases". The check this rule replaces uses exact string equality on labels, and an alias at a relation end is removed earlier as dangling (Context). This draft therefore defines the rule by exact equality and records the alias cases as dangling drops, so the rule "matches exactly the check it replaces". Accept this, or ask for normalised comparison. That would be a broader rule: it would also catch label-vs-alias pairs before `drop_dangling`, and they would count as self-relations rather than dangling.
2. **The v1 Day 4 outputs.** The runner will remove the superseded v1 extract directory when v2 is published. Copy `extract.json` (counts) and, if wanted, `extraction.json` into `docs/evidence/m7/session3/` before the rerun, or rely on the m7_verify results file?

## Gate / revisit when

- The rule is accepted when (a) passes and (b) is recorded. (c) shows that the stage changed only where (b) predicts. Revisit if a later model, prompt or harness change is evaluated: that evaluation would have to decide whether the harness should adopt the same rule, under a new harness version.
- Revisit together with the ADR for decision (a) (keep the model loaded), which changes `extract.stage.keep_alive` and must state its own expected effect on the request test.
