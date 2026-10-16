# ADR-0048: M7 extraction schema, gold set and gate rules

Status: Accepted
Amended: 2026-10-17, Amendments 1 (single labeller) and 2 (comparison C4, labelling order) at the end
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
