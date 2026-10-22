# ADR-0048: M7 extraction schema, gold set and gate rules

Status: Accepted
Amended: 2026-10-17, Amendments 1 (single labeller), 2 (comparison C4, labelling order) and 3 (second annotator on the Day 4 shared windows); 2026-10-18, Amendment 4 (correcting invalid relations in Day 4 gold windows); 2026-10-20, Amendment 5 (Day 4 gold v2 relabelling pass); 2026-10-22, Amendment 6 (adding concepts in the gold v2 pass); all at the end
Date decided: 2026-10-15
Date recorded: 2026-10-15
Module: M7

Amends ADR-0020: the importance field is `important` with a `cue`, not the draft `exam_relevant`. It also replaces the "10 labelled windows" extraction gate in the `docs/BUILD_ORDER.md` pending decision "M0 / M7 / M11: qwen3.5 VRAM headroom" with comparison C1 below.

## Context

M7 adds LLM extraction of concepts, relations, importance (F4) and `is_recap` (F20) per window. It leaves three choices open:

- the LLM: qwen3.5 against Gemma 4 E4B (ADR-0002, ADR-0012);
- the LLM input: the original-language transcript or a per-window English translation (ADR-0041);
- the unit of extraction: one window per call, or several.

The BUILD_ORDER exit is precision and recall against human-labelled concepts on 2 lectures, plus an LLM choice.

As in M5 (ADR-0043), every rule that decides these choices is fixed here, before any model output exists, so that no rule can be tuned after seeing a result.

The gold set must be made by people, or the M7 numbers would measure the model against itself.

The dev lecture, Day 4, is 688.03 s long. On the 30 s grid (ADR-0045) that is 23 non-empty windows, so a 40-window sample cannot be drawn from it. Three of the 23 are reserved as worked examples for the labelling guide.

## Decision

**1. Extraction schema, version 1.** The JSON Schema is `backend/src/insightex/extract/extraction.schema.json`. The validator is `backend/src/insightex/extract/extraction_schema.py`, written with the standard library only. Byte-identical copies are kept in `tools/label_concepts/`, because tools never import `backend/`. A test fails if the copies differ.

Gold labels and model output use the same schema. A document has these fields:

- `schema_version` (1);
- `lecture_id`;
- `producer`: `{kind: human|model, name}`;
- `sample_manifest_sha256`: optional, used by gold files;
- `windows`: one record per window.

Each window record has these fields:

- `window`: `{lecture_id, window_index, start_s, end_s}`. `window_index` is the window id from the index stage's `windows.json`, on the fixed 30 s grid of ADR-0045;
- `concepts`: a list of `{label, aliases[]}`. `label` is the canonical English label (textbook usage, ADR-0029). `aliases` holds the other names the speaker said;
- `relations`: a list of `{head, type, tail}`, where `type` is one of `prerequisite_of`, `part_of`, `example_of` or `contrasts_with`. The meanings are in `docs/labelling/m7_concepts.md`. `contrasts_with` is symmetric;
- `important`: a boolean;
- `cue`: a non-empty English note when `important` is true, otherwise null;
- `is_recap`: an optional boolean. It is not labelled in gold and not gated (F20 is Exploratory).

The validator also enforces rules that a JSON Schema cannot express:

- relation endpoints must be concept labels from the same window;
- head and tail must differ;
- relations must not repeat (direction counts, except for `contrasts_with`);
- no two concepts may share a name after normalisation, whether label or alias;
- a name must not be empty after normalisation;
- `end_s` must be greater than `start_s`;
- `window_index` values must be unique;
- every window's `lecture_id` must equal the document's.

**2. Data split.**

- **Dev lecture: Day 4** (`sha256-de27cb67c2acbedebd0c2c7416932b8a`). All prompt iteration and all arm comparisons happen on it.
- **Prompt freeze.** Prompt iteration on the dev lecture uses qwen3.5 only. The extraction prompt is frozen before C1 runs, and its sha256 is recorded in the C1 evidence. Both C1 arms run that frozen prompt. If Gemma 4 E4B wins C1, the frozen prompt is re-checked on it (the validity rule, and a read-through of its output), but there is no Gemma-specific tuning. A prompt change after the freeze is a new freeze with a new hash, and every comparison already run on the old prompt is re-run.
- **Held-out lecture:** a second lecture, chosen and ingested later. It must be:
  - in Hindi, while Hindi is the only tested language (ADR-0040); lectures transcribed with an untested language are excluded, and the sampler refuses them;
  - by a different speaker;
  - at least 20 minutes long (at least 40 windows).
- The held-out lecture is used **once**, for the final configuration only, with no tuning after seeing it. A crash may be fixed and the run repeated. If a prompt, model or setting is changed after held-out scores have been seen, the held-out numbers are reported as contaminated.

**3. Gold set.** The labelling tool is `tools/label_concepts`, and the labelling rules are `docs/labelling/m7_concepts.md`.

- **Dev: N = 20.** This is the census of the Day 4 windows that remain after three are reserved as guide examples. Each reason is recorded in the sample manifest and the guide:
  - window 0: a passing mention, not labelled;
  - window 3: an explicit importance cue;
  - window 5: a stated relation.
  
  10 of the 20 windows are shared, and the other 10 are split 5 and 5.
- **Held-out: N = 40.** The windows are sampled with a seed, stratified across the timeline, and recorded in the sample manifest. 10 are shared, and the other 30 are split 15 and 15.
- The shared windows are labelled independently by Bilal and Fatima. Their agreement, computed on those first, pre-discussion files, is the **human ceiling**.
- After the discussion, an agreed consensus version of the shared windows enters the gold set. The other windows enter from the labeller each one is assigned to.
- No labels are made or pre-filled by an LLM or by Claude, and nobody sees model output for a lecture before its gold set is merged.

**4. Concept matching.**

- **String rule.** A model concept matches a gold concept if, after normalisation, its label or any alias equals the gold label or any gold alias. Normalisation is NFKC, then case-folding, then removing punctuation (Unicode P*), whitespace and separators (Z*) and format characters (Cf, such as the zero-width non-joiner).
- **One-to-one.** A gold concept matches at most one model concept. The pairs are a maximum bipartite matching over the string-rule edges. It is deterministic: Kuhn's algorithm, run in list order.
- **Adjudication (blind).** Model concepts still unmatched after the string rule go to an adjudication sheet. Bilal marks each one as a match to a named gold concept of the same window, or as no-match.
  - For a comparison, the sheet **pools the unmatched concepts from all arms being compared**. It removes duplicates (the same window and the same normalised label count once, whichever arms produced it) and shuffles the entries with a recorded seed. **No arm is shown.** Each entry shows the window, the model concept with its aliases, and that window's gold concepts.
  - Every decision is made before any arm is scored with adjudication.
  - Decisions are stored in `tools/label_concepts/labels/<lecture_id>/adjudications.json`, keyed by (window_index, normalised model label). The file is append-only and frozen: an entry is never changed once a score has been reported with it, and every later run reuses it.
  - An adjudicated match is used only if that gold concept is still unmatched.
  - Unmatched concepts with no entry yet count as false positives until they are decided.

**5. Relation match.** A model relation matches a gold relation when both endpoints map, through the concept matching, to the gold relation's endpoints and the types are equal. Direction counts, except for `contrasts_with`. Relations are compared as sets.

**6. Metrics.**

- **Primary: concept precision, recall and F1, micro-averaged over windows** (summed true positives and set sizes), computed with adjudication applied. This figure decides the comparisons (section 7). The string-rule-only figure is reported next to it.
- **Headline comparison with the human ceiling: string rule only on both sides.** The ceiling (human agreement on the shared windows) is computed with the string rule only. It is compared only with the model's string-rule-only concept F1 on the same lecture. The adjudicated model F1 is reported separately and is **never** compared with the ceiling, because only the model's concepts get adjudicated, which would favour the model.
- Reported secondaries, which never decide a comparison:
  - relation P/R/F1;
  - importance P/R over windows;
  - the number of **dropped relations** per arm (see the validity rule in section 7);
  - the human ceiling (agreement on the shared windows, string rule only; compared only with the model's string-rule-only F1, as above).
- **Per-window F1** is 1.0 when both the model and gold have no concepts, and 0 when only one side has none.

**7. Comparison noise rule (dev lecture, N = 20).**

- Compute per-window concept F1 for both arms. A window is a win for the arm whose F1 is higher.
- **Net wins of 2 or fewer is a tie.** A tie keeps the simpler or cheaper arm: the model with the smaller measured VRAM peak at the worst-case prompt (C1), original-language input (C2), and single-window calls (C3).
- **A change is adopted only if it has net wins of 3 or more AND its micro concept F1 is not lower.**
- **Validity rule: every window must be valid after one retry.** A window is valid if its record passes the v1 validator, either on the first response or on one retry of the same call. An arm with any invalid window is rejected, regardless of its score.
  - **Dangling relations do not make a window invalid.** Before validation, a relation whose head or tail is not in that window's concept list is dropped. The number dropped is counted and reported per arm. Every other validator rule still applies.
- **If both arms of a comparison fail the validity rule,** fix the validation or retry handling. That fix is a new prompt freeze (new hash), and both arms are re-run. **Never pick the arm that failed less.**
- At N = 20, one window is 5% of the set, so ties are more likely than at 40, and a tie defaults to the simpler arm.

**8. Arms (to be run in Session 2, not now).**

| Comparison | Arm A (kept on a tie) | Arm B | Held fixed |
|---|---|---|---|
| C1 | the model with the smaller VRAM peak at the worst-case prompt | the other model (qwen3.5 vs Gemma 4 E4B) | original transcript, single window |
| C2 | original transcript | per-window English translation (ADR-0041), made by the C1 winner | C1 winner, single window |
| C3 | single 30 s window per call | batches of k windows | C1 and C2 winners |

- The comparisons run in the order above, each on the winner of the one before.
- **C2 translator.** The translation is made by the C1 winner through Ollama (the ADR-0002 call contract), with one fixed translation prompt. That prompt is frozen and its sha256 recorded before C2 runs, under the same rule as the extraction prompt. Translations are cached as their own stage, one per window, keyed by the window text's sha256, the model and the prompt hash, so that extraction reruns reuse them. The translation's wall time and VRAM peak count against arm B's cost. A tie keeps original-language input.
- **C3 batch size k** is fixed before C3 runs. It is the largest value in 3 to 5 that passes both of these checks:
  - the worst-case k-window prompt plus `num_predict` fits the `num_ctx` measured and chosen in Session 2, under the ADR-0002 budget rule;
  - at that prompt, `ollama ps` shows 100% GPU.
  
  If no k in 3 to 5 passes, C3 is not run, and single-window calls stay.
- For every arm, the run records:
  - VRAM peak;
  - tokens per second;
  - `num_ctx`;
  - `ollama ps` (size and PROCESSOR) at the worst-case prompt.

**9. Exit** (from BUILD_ORDER): precision and recall reported on both lectures, and an LLM choice decided. M7 has no P/R pass bar. The numbers feed M17.

## Alternatives considered

- **40 dev windows.** Impossible: Day 4 has 23 windows.
- **Label all 23 Day 4 windows and take guide examples from another lecture.** This gives a slightly larger dev set, but the examples would be off-topic and there was no on-topic source. Rejected by Bilal on 2026-10-15.
- **Use a longer dev lecture.** This would block labelling until one is ingested. Day 4 is the lecture every other gate used.
- **Exact string match without aliases.** Code-switched speech names one idea in several scripts and spellings. Aliases turn those into a checkable rule instead of a judgement call.
- **Embedding or LLM similarity for matching.** That would let a model grade a model, and it has thresholds to tune. Human adjudication is frozen and auditable instead.
- **Adopting a change on any F1 gain.** With 20 windows, one window is 5 points. The net-3 rule demands a margin, as ADR-0043 did for retrieval.
- **Macro-averaged F1 as the primary metric.** Windows with one concept would swing it. Micro F1 weights every concept equally. The per-window F1 is used only for the win/loss count.

## Consequences

- Production extraction (Session 3) writes v1 records and imports `insightex.extract.extraction_schema`. The Ollama `format` may be a subset of the schema, covering only the parts the model fills, but stored output is a full v1 record.
- Any change to the schema bumps `schema_version`, updates both copies, and re-validates the gold files.
- Gold files and adjudications are committed under `tools/label_concepts/labels/`. They contain short surface forms from the lectures (aliases), as does the guide's worked examples section. Both are added to the M20 list of lecture-derived text to review before the repo goes final.
- The held-out numbers come from one run of one configuration, so they carry no comparison and are only reported.
- The extraction prompt is iterated on 20 windows with qwen3.5 only, so it may overfit those windows and that model. The held-out lecture is the check on the first; on the second, Gemma gets no tuning of its own, so C1 is tilted towards qwen3.5. A tie already favours the smaller model, so this is accepted and recorded.

## Evidence

- Day 4: 688.03 s, 23 windows. The labelling tool's grid matches the index stage's `windows.json` exactly (checked by `sample`, which refuses to run on a mismatch).
- No model output exists. This ADR is written before any extraction has run.
- Tool and tests: `tools/label_concepts/` (README, `tests/`), and `backend/tests/unit/test_extraction_schema.py`.

## Gate / revisit when

Accepted by Bilal on 2026-10-15, before Session 2 and before any model output existed, after four review rounds and a by-hand browser check of the labelling tool (passed 2026-10-15). The rules above are now frozen: any change is a new ADR, made before the affected comparison runs.

Revisit:

- when the held-out lecture is chosen (confirm it is Hindi, a different speaker and at least 20 minutes);
- if the shared-window discussion changes a definition in a way that affects matching;
- if the validity rule keeps rejecting both arms after a fix.

## Amendment 1 (2026-10-17): single labeller

Decided by Bilal on 2026-10-17. Fatima will not label. The Accepted text above is kept as it was; where it conflicts with this amendment, this amendment applies. No model output existed when it was made (no extraction has run), so no comparison is affected.

- **One labeller.** Bilal labels every gold window of both lectures.
  - Day 4 dev gold: all 20 eligible windows (the same census, windows 0, 3 and 5 still reserved), labelled by Bilal.
  - Held-out gold: 40 sampled windows, labelled by Bilal. The sample still marks 10 of them as shared.
  - The Day 4 sample is not re-drawn: same windows, same seed, same 10 shared windows. Only the assignment changes, and the change is recorded in `sample.json` (`amendments`, with the previous manifest's sha256). Labels files made against the previous manifest stay valid.
- **The human ceiling is replaced by an intra-rater check.** At least 2 days after finishing all his windows, Bilal re-labels the 10 shared windows blind (without opening his first labels) as labeller `bilal_repeat`. Agreement between `bilal` and `bilal_repeat`, string rule only, on the first (pre-revision) `bilal` labels, is reported as the **consistency figure**.
  - It is not an inter-annotator ceiling and is never called one. Every report describes the gold set as **single-annotator** and the figure as single-annotator (intra-rater) consistency.
  - Section 6's fairness rule still holds for it: it is shown only next to the model's string-rule-only concept F1, never next to the adjudicated F1.
- **The consensus step is replaced by a revision.** The differences between `bilal` and `bilal_repeat` take the place of the shared-window discussion and may prompt the one guide update. After that update, Bilal revises his own labels (all his windows) under the updated guide. **Gold = Bilal's revised labels.** The pre-revision `bilal.json` and the agreement report are committed before revising, so the consistency figure stays tied to the files it was computed from.
- Adjudication (section 4) was already Bilal's alone and is unchanged.
- The tool keeps `fatima` and `consensus` working, so a second labeller can join later. That would need a new sample manifest or amendment and a new ADR amendment, made before any model output exists for that lecture.

Consequence: with one annotator there is no measure of how far another person would disagree. The gold set carries Bilal's reading of the guide, and the consistency figure bounds only his own repeatability, not inter-annotator agreement.

## Amendment 2 (2026-10-17): comparison C4 (previous-window context) and the labelling order

Decided by Bilal on 2026-10-17, before any model output existed (no extraction has run). The text above and Amendment 1 are kept; where they conflict with this amendment, this amendment applies.

**Why.** The one rule update to the labelling guide (17 Oct 2026, prompted by Bilal's first pass, in which 7 windows explained a concept without naming it) adds "Unnamed concepts": when a window explains something substantive about a concept without saying its name, the concept is labelled, and the earlier part of the lecture is used only to identify which concept is meant. So the gold set labels some concepts by the lecture's flow, and a model that sees one window alone cannot recover them. C4 measures whether giving the model the previous window recovers them without adding false positives.

**C4: previous-window context.**

| Comparison | Arm A (kept on a tie) | Arm B | Held fixed |
|---|---|---|---|
| C4 | window text only | the previous window's text supplied as read-only context, clearly marked as not to be extracted from | C1, C2 and C3 winners |

- C4 runs after C3, on the C1 to C3 winners, under the same noise rule and validity rule (section 7). Scoring is unchanged: per window, against that window's gold. A concept the model takes from the context counts as a false positive like any other.
- **The previous window** is the window just before it in the lecture's grid (`window_index - 1`, so the previous non-empty window, ADR-0045), whether or not that window is in the gold sample. The reserved guide windows (0, 3, 5) are used as context like any other. The lecture's first window has no context, so its arm B input equals arm A.
- **Language.** The context is in the same form as the extracted window: the original transcript if C2 kept original input, or the cached English translation if C2 adopted translation.
- **Prompt freeze.** Arm B is the frozen extraction prompt plus one fixed context block (a delimited "previous window, for reference only; do not extract from it" section). The block's text is fixed before C4 runs, and the sha256 of the arm B prompt is recorded in the C4 evidence, under the section 2 freeze rule. There is no tuning of the block after seeing C4 output.
- **Context budget.** Arm B's worst-case prompt (the longest window with the longest previous window, or the worst-case batch with its context) plus `num_predict` must fit the `num_ctx` chosen in Session 2 under the ADR-0002 budget rule, at 100% GPU in `ollama ps`. If it does not fit, C4 is not run, is reported as not run, and window-only input stays. Arm B's extra tokens, wall time and VRAM peak are recorded and count against it.
- **With batching (if C3 adopted batches of k windows).** Each batch gets the previous window of its first window as read-only context. A later window in the batch needs no context when the window before it in the batch is its previous grid window. When it is not (as can happen in a sampled held-out set), its own previous window is added to the context block too, labelled with the window it precedes. Context windows are never extraction targets.

**Labelling order (corrects Amendment 1).** The rule update comes after the first pass. Bilal then revises all his labels under the updated guide and labels the remaining windows (Day 4: 6, 10, 14, 18, 22), and validates and commits `bilal.json`. Only then, at least 2 days later, does he re-label the 10 shared windows blind as `bilal_repeat`, so that the repeat is made under the same guide. The consistency figure is `bilal` (finished) against `bilal_repeat`, string rule only. Gold is that finished `bilal.json`. Differences found by the repeat are reported and change neither the guide nor the gold. The guide is frozen after the rule update; the held-out lecture is labelled under it with no rule update. This replaces Amendment 1's "consistency on the first (pre-revision) labels, then review, update and revise".

## Amendment 3 (2026-10-17): a second annotator on the Day 4 shared windows

Decided by Bilal on 2026-10-17, before any model output existed (no extraction has run on any lecture). The text above and Amendments 1 and 2 are kept; where they conflict with this amendment, this amendment applies.

- **Fatima labels the 10 shared Day 4 windows** (2, 4, 8, 9, 11, 13, 16, 17, 19, 21) as a second annotator, labeller name `fatima`.
  - She labels blind: she does not see `bilal.json` or any of Bilal's labels, before or during her labelling. The tool serves only her own file.
  - She labels under the current, frozen guide. The guide's one rule update is already used, so the guide does not change because of her labels or the disagreements.
  - The Day 4 sample is not re-drawn. The manifest records her as a shared-windows-only annotator (an entry under `amendments` with the previous manifest's sha256). Bilal's labels files stay valid.
- **Inter-annotator figure.** Agreement between `bilal` and `fatima` on the 10 shared windows, string rule only, is the inter-annotator agreement figure. It is computed on Bilal's labels as they were before his review (below), and that file is kept as `bilal_pre_review.json`. Section 6's fairness rule holds: it is shown only next to the model's string-rule-only concept F1 on the same lecture, never next to the adjudicated F1.
- **Gold stays Bilal's labels.** There is no consensus step and Fatima's labels never enter the gold set.
- **Review.** After the agreement is computed, Bilal reviews the disagreements on the shared windows. He may correct clear errors in his own labels on those windows. Every correction is logged with its reason (window, reason, the record before and after) in `corrections_bilal.json`. `validate` refuses a `bilal.json` whose shared windows differ from `bilal_pre_review.json` without a matching logged correction, and refuses any change to a non-shared window after the review starts. Gold is the reviewed `bilal.json`.
- **The `bilal_repeat` intra-rater check is dropped.** Amendment 1's consistency figure is replaced by the inter-annotator figure above, and the 2-day wait goes with it.
- Reports describe the gold set as made by one annotator (Bilal), with a second annotator's labels on 10 shared windows used for agreement and for reviewing his labels.
- **Held-out lecture:** this amendment covers Day 4. Whether a second annotator labels the held-out lecture's shared windows is decided, in a new amendment, before that lecture is sampled.

Consequence: the agreement figure measures two people on 10 windows, so it is noisy (one window is 10% of the set). Corrections after the review can move the gold set towards Fatima's reading on the shared windows; the figure itself is computed on the pre-review file, so the corrections cannot raise it, and the log makes each one auditable.

## Amendment 4 (2026-10-18): correcting invalid relations in Day 4 gold windows

Decided by Bilal on 2026-10-18, before any model output on a real lecture. The text above and Amendments 1 to 3 are kept; where they conflict with this amendment, this amendment applies.

**Context.** During the Day 4 agreement review, the first annotator's part_of relations in non-shared windows 14 and 15 were found to be invalid: "Batch Learning part_of Problem With Batch Learning" states that batch learning is a component of its own problem. Reversing it is also false, and none of the four relation types describes a weakness of a concept. The guide says a missing relation costs less than an invented one. Amendment 3 allows corrections on shared windows only, so these relations could not be corrected. After the review the Day 4 gold has three relations, two of them these.

**Decision.** In any Day 4 gold window, a relation may be deleted when the guide's own definition of its type does not hold for its two concepts, or reversed when the definition holds only in the other direction. Concepts, aliases and the importance flag may not change under this amendment. Each correction is logged with `log-correction` and its reason, as in Amendment 3. The guide does not change. The test is the guide's type definitions, not the second annotator's labels or any model output; no extraction has run on a real lecture.

**Consequence.** Windows 14 and 15 lose their part_of relations. The Day 4 gold then has one relation (window 16), so Day 4 relation P/R is reported but is not meaningful; relation extraction is evaluated on the held-out lecture. The amendment does not apply to the held-out lecture.

## Amendment 5 (2026-10-20): Day 4 gold v2, a relabelling pass under the guide's explanation rule

Decided by Bilal on 2026-10-20, before any gold label was changed. The text above and Amendments 1 to 4 are kept; where they conflict with this amendment, this amendment applies.

**Context.** Day 4 gold v1 (`gold.json`, sha256 `7fcec636170248ed48df8badacf2b40dc1c8edfc96aa073cf8ef90ec58b8a4ff`, tag `m7-day4-gold-frozen`; 20 windows, 27 concepts, 1 relation) breaks the labelling guide in two ways:

1. Concepts were labelled as soon as a window named them, without checking that the window explains them or uses them substantively. The guide applies that test to every concept, named or unnamed ("Label a concept only if this window explains it or uses it substantively").
2. One concept has different names in different windows, for example "Problem With Batch Learning" and "Problem Of Batch Learning". The guide's canonical label gives a concept one name.

**What had been seen when this was decided.**

- **C1 (run 18 Oct 2026; harness 7, prompt `c7e061fc…4648`).** Both arms ran on the 20 windows. Bilal was shown only validity, wall time, the VRAM peaks, and the adjudication sheet's path and item count. No C1 score, matched count, output or per-window result was computed or shown. Bilal stopped the adjudication before opening the sheet (`adjudication_sheets/C1-20261018T180252Z.json`, 20 entries, made against gold v1). That sheet is void: it is never decided or used.
- **Prompt iteration (18 Oct 2026, qwen3.5 only).** Bilal does not recall reading the per-window details in the reports he approved each version from (`docs/evidence/m7/session2b_prompt_iteration.md`), but they were shown to him, so this amendment treats them as seen. Those reports contained some qwen3.5 output from versions 1 to 4:
  - micro scores against gold v1;
  - the missed gold concepts per window;
  - the extra model concepts by window, with their labels (for example window 4, "online learning");
  - the windows where the model returned no concepts;
  - the relations the model invented.
- **Gemma.** No Gemma output has been shown.
- **The earlier mismatch.** The gold/guide mismatch on "problem of batch learning" concepts was already recorded in those reports as fixed rule 7 (18 Oct 2026, before version 1 ran).

**Decision.**

1. **Gold v1 stays unchanged.** `gold.json` and its tag are not changed, and results already reported against gold v1 stay as v1 results.
2. **Gold v2 comes from one relabelling pass.** Bilal relabels all 20 Day 4 windows once, starting from the gold v1 labels, under the frozen guide (the guide does not change). For each gold v1 concept he either keeps it or removes it:
   - **Remove:** the window does not explain the concept or use it substantively.
   - **Keep:** the concept stays, and may be renamed to the one canonical name used for that concept in every window.
   - **Relations follow:** removing a concept removes its relations, and renaming a concept renames them.
   - **Nothing else changes:** no concept is added, and aliases, the importance flag and the cue stay as in v1. The one exception is an alias that becomes the same as the new label, which is dropped.
   - **Reasons:** every removal and every rename needs a reason. Every change is logged with its time and reason in `relabel_v2.json`.
   - **Tool:** `label_concepts.py relabel-start`, `relabel-serve`, `relabel-status` and `relabel-merge`. The page shows the window's text, its video and the gold v1 labels, and no model output.
3. **Gold v2's files.** Gold v2 is `gold_v2.json`, frozen with the tag `m7-day4-gold-v2-frozen`. It has its own adjudication file (`adjudications_v2.json`), and no decision made against gold v1 is reused.
4. **After the freeze, with no new model runs:**
   - **a. Re-score the prompt versions.** The saved prompt-iteration outputs of versions 1 to 4 are scored against gold v2: micro concept F1, string rule, no adjudication, as in the iteration. Only the F1 of each version is reported. The best version is chosen by the existing rules: the highest F1, and on a tie the earlier version (fixed rule 8).
   - **b. If version 2 still wins:** the two existing C1 runs are scored against gold v2, without showing the scores, and a new blind adjudication sheet is made against gold v2 under section 4. C1 stays blinded until those decisions are frozen.
   - **c. If another version wins:** everything stops, and nothing is re-run without Bilal's decision. A different prompt would be a new freeze, and under the prompt freeze rule every comparison already run on the old prompt is re-run.
5. **The inter-annotator figure is open, to be decided separately.** The v1 figure (0.240, `bilal_pre_review.json` against `fatima.json`) was measured on labels that this pass replaces. Until this is decided, scoring against gold v2 reports no inter-annotator figure.

**Consequences.**

- **Gold v2 is not blind to model behaviour on Day 4.**
  - The pass is driven by the guide, but the iteration reports Bilal had read list qwen3.5's extra and missed concepts by window.
  - Removing gold concepts that those reports showed qwen3.5 missing raises qwen3.5's scores, and no Gemma output was shown.
  - So the Day 4 re-score of the prompt versions, and C1 against gold v2, may favour the prompt and the model whose output was seen. This adds to the tilt towards qwen3.5 recorded in the Consequences above, and it is recorded in the same way.
  - The held-out lecture, labelled under the frozen guide before any model reads it, remains the unbiased check of the final configuration.
- **Relation scores.** Day 4 relation scores remain not meaningful.
- **Scope.** The amendment applies to the Day 4 gold only.

## Amendment 6 (2026-10-22): adding concepts in the Day 4 gold v2 pass

Decided by Bilal on 2026-10-22, before any concept was added. The text above and Amendments 1 to 5 are kept; where they conflict with this amendment, this amendment applies. Amendment 5's record of what had been seen is unchanged.

**Context.** Amendment 5 lets the gold v2 pass keep, remove or rename gold v1 concepts only. Some Day 4 windows explain or use substantively a concept that gold v1 never labelled. Gold v2 should follow the guide in both directions: no concept the guide leaves out, and none it requires missing.

**Decision.**

1. **Adding is allowed.** In the Day 4 gold v2 pass, a concept may be added to a window, under the frozen guide (the guide does not change). A concept is added only if the window explains it or uses it substantively. This includes a concept the window does not name, under the guide's "Unnamed concepts" rule: earlier windows only identify which concept is meant.
2. **What an addition holds.** An addition has:
   - a canonical English label, chosen from the labels in use when the concept already has a name elsewhere;
   - aliases, which are only names said in this window, copied as written;
   - a reason.
3. **What an addition does not hold.**
   - **No importance.** The importance flag and the cue belong to the window, not to a concept (schema v1 and the guide), and Amendment 5 keeps them unchanged, so an addition carries none.
   - **No relations.** Adding a relation would need a further amendment.
4. **Logging.** Every addition, every change to one, and every withdrawal before the merge is logged in `relabel_v2.json` with its time and reason, like the other changes.
5. **Validation.** The validator rules still apply, for example no name used twice in a window after normalisation.
6. **Decisions already made stay.** The decisions already recorded in `relabel_v2.json` are kept.

**Consequences.**

- **Count.** Gold v2 may now have more concepts than gold v1 in a window.
- **The tilt applies to additions too.** The tilt towards qwen3.5 recorded in Amendment 5's Consequences applies to additions in the same way: an added concept that qwen3.5's reported output already contained raises its score.
- **Scope.** The amendment applies to the Day 4 gold only.
