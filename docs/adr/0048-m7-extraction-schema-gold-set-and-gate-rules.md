# ADR-0048: M7 extraction schema, gold set and gate rules

Status: Proposed
Date decided: not decided; proposed 2026-10-15
Date recorded: 2026-10-15
Module: M7

On acceptance this ADR amends ADR-0020: the importance field is `important` with a `cue`, not the draft `exam_relevant`. It also replaces the "10 labelled windows" extraction gate in the `docs/BUILD_ORDER.md` pending decision "M0 / M7 / M11: qwen3.5 VRAM headroom" with comparison C1 below.

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
- **Adjudication.** Model concepts that are still unmatched go to an adjudication sheet. Bilal marks each one as a match to a named gold concept of the same window, or as no-match.
  - On the sheet, each entry shows the window, the model concept and the gold concepts, but **not the arm** that produced it.
  - Decisions are stored in `tools/label_concepts/labels/<lecture_id>/adjudications.json`, keyed by (window_index, normalised model label). The file is append-only and frozen: an entry is never changed once a score has been reported with it, and every later run reuses it.
  - An adjudicated match is used only if that gold concept is still unmatched.
  - Unmatched concepts with no entry yet count as false positives until they are decided.

**5. Relation match.** A model relation matches a gold relation when both endpoints map, through the concept matching, to the gold relation's endpoints and the types are equal. Direction counts, except for `contrasts_with`. Relations are compared as sets.

**6. Metrics.**

- **Primary: concept precision, recall and F1, micro-averaged over windows** (summed true positives and set sizes), computed with adjudication applied. The string-rule-only figure is reported next to it.
- Reported secondaries, which never decide a comparison:
  - relation P/R/F1;
  - importance P/R over windows;
  - the **JSON-valid rate after one retry**, counted per window. A window is valid if its record passes the v1 validator on the first response, or on one retry of the same call;
  - the human ceiling (agreement on the shared windows, string rule only, so it is a conservative bound).
- **Per-window F1** is 1.0 when both the model and gold have no concepts, and 0 when only one side has none.

**7. Comparison noise rule (dev lecture, N = 20).**

- Compute per-window concept F1 for both arms. A window is a win for the arm whose F1 is higher.
- **Net wins of 2 or fewer is a tie.** A tie keeps the simpler or cheaper arm: the model with the smaller measured VRAM peak at the worst-case prompt, original-language input, and single-window calls.
- **A change is adopted only if it has net wins of 3 or more AND its micro concept F1 is not lower.**
- **An arm with a JSON-valid rate below 98% is rejected regardless of its score.** With 20 dev windows, or 40 held-out, that allows no invalid window at all.
- At N = 20, one window is 5% of the set, so ties are more likely than at 40, and a tie defaults to the simpler arm.

**8. Arms (to be run in Session 2, not now).**

| Comparison | Arm A (kept on a tie) | Arm B | Held fixed |
|---|---|---|---|
| C1 | the model with the smaller VRAM peak at the worst-case prompt | the other model (qwen3.5 vs Gemma 4 E4B) | original transcript, single window |
| C2 | original transcript | per-window English translation (ADR-0041) | C1 winner, single window |
| C3 | single 30 s window per call | batches of k windows | C1 and C2 winners |

- The comparisons run in the order above, each on the winner of the one before.
- k is fixed before C3 runs. It is the largest value in 3 to 5 whose worst-case prompt plus `num_predict` fits `num_ctx` 8192 at 100% GPU, under the ADR-0002 budget rule.
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
- The extraction prompt is iterated on 20 windows, so it may overfit them. The held-out lecture is the check on that.

## Evidence

- Day 4: 688.03 s, 23 windows. The labelling tool's grid matches the index stage's `windows.json` exactly (checked by `sample`, which refuses to run on a mismatch).
- No model output exists. This ADR is written before any extraction has run.
- Tool and tests: `tools/label_concepts/` (README, `tests/`), and `backend/tests/unit/test_extraction_schema.py`.

## Gate / revisit when

This ADR becomes Accepted when Bilal approves it before Session 2 starts. After that, the rules above are frozen: any change is a new ADR, made before the affected comparison runs.

Revisit:

- when the held-out lecture is chosen (confirm it is Hindi, a different speaker and at least 20 minutes);
- if the shared-window discussion changes a definition in a way that affects matching;
- if the JSON-valid rule rejects every arm.
