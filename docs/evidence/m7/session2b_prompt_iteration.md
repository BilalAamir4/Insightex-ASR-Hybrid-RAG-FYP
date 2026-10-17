# M7 Session 2b, part 2: extraction prompt iteration (qwen3.5, Day 4 dev lecture)

Lecture `sha256-de27cb67c2acbedebd0c2c7416932b8a` (Day 4). Gold: `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/gold.json`, sha256 `7fcec636…a4ff`, 20 windows. This is the first stage in which a model reads Day 4. Harness rules: ADR-0048 and ADR-0049.

## Fixed rules (recorded 18 Oct 2026, before version 1 runs)

1. **Version limit:** at most 5 prompt versions.
2. **Every change must be named:** each change after version 1 names a failure seen in the previous run (its category, the count and the window indices) and says how the change addresses it. No exploratory changes.
3. **No gold-window text:** no text from the 20 gold windows goes in the prompt. Examples come only from the reserved windows 0, 3 and 5 (as worked in `docs/labelling/m7_concepts.md`) or are invented. No window-specific rules.
4. **Stop rule:** stop when every window is valid after the one retry and micro concept F1 (string rule) has not improved for two consecutive versions, or after version 5. Freeze the best-scoring version.
5. **Settings:** qwen3.5 only, with the C1 settings: single-window calls, original language, no previous-window context. Gemma does not run in this stage.
6. **Approval:** every version is approved by Bilal before it runs. After each run, the next change is proposed with its named reason and waits for approval.
7. **Known gold/guide mismatch (added 18 Oct 2026, before version 1 runs).** "The prompt follows the labelling guide, not the gold's labelling habits. The gold labels a problem or disadvantage of batch learning as its own concept in windows 10–16 and 20, while the guide counts 'a problem of it' as explaining that concept. A model labelling 'batch learning' there is a guide-consistent reading. This is recorded as a known gold/guide mismatch and is not a named failure for prompt changes."

Each run is scored with `tools/label_concepts` (`score`, string rule) and reported as:
- validity: windows needing the retry, windows still invalid;
- micro concept P/R/F1 and relation P/R/F1;
- failures grouped by category, with window indices.

## Versions

| Version | File | sha256 | Status |
|---|---|---|---|
| 1 | `config/prompts/m7_extraction_v1.txt` | `d2a50e58ac5cb630e69516d59d537d9574de18ec926c187826434bafa696f6a8` | approved as drafted, 18 Oct 2026; run, concept F1 0.340 |
| 2 | `config/prompts/m7_extraction_v2.txt` | `c7e061fce838d935c7335b01746fbec8c708f2d1f3845720c8e5728ac7154648` | approved 18 Oct 2026 with conditions: version 1 + change (a) and (b) only |

### Version 1 notes

- **Built from the guide's rules:** the concept definition and substantive test, canonical English labels, aliases copied exactly as written, the four relation types with their directions, importance signals and the cue, and `is_recap` always false.
- **Examples:** the guide's English glosses of reserved windows 0, 3 and 5, plus invented example A (learning rate). The window 5 gloss was reworded slightly ("training uses the whole of your data at once, with no incremental training"), because the guide's wording shared five consecutive words with gold window 14's transcript. After the rewording, no 5-word sequence of the prompt occurs in any gold window's transcript text. One 4-word sequence ("types of machine learning", from the reserved-window glosses) occurs in gold window 1; it is a generic phrase. This was checked by script; only counts were printed, plus the shared phrase from the prompt side.
- **"Unnamed concepts":** the guide lets a labeller use the earlier lecture to identify an unnamed concept. The C1 settings give the model only the window, so version 1 asks it to include an unnamed concept only when the window's own text makes clear which concept it is.
- **Size:** 6,892 characters. The instructions are 1,900 estimated tokens, about 1,230 real tokens on qwen3.5 at the measured 0.647 ratio (not measured). The placeholder used for the k measurements was about 920 real tokens. The k decision is made after the freeze with the real prompt (ADR-0049).

## Version 1 run (18 Oct 2026)

- **Run:** `insightex extract-eval run --arm C1-qwen3.5` on the 20 gold windows (`sample.json`). Settings: qwen3.5 digest `44a38603…a399f`, harness version 4, prompt `d2a50e58…f6a8`, `num_ctx` 8192, `num_predict` 1024, temperature 0, seed 42, think false, `keep_alive` 0, single-window calls, original language, no context.
- **Evidence:** `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/prompt_iteration/v1/` (`extraction.json`, `run.json`, `calls.jsonl`, `score.json`).
- **Cost:** wall time 149.4 s for 20 calls (mean load 4.41 s per call), 61.1 tokens/s, largest prompt 1,742 real tokens. VRAM peak 7,752 MiB (5,549 above a 2,203 MiB baseline), `ollama ps` 100% GPU.
- **Prompt size:** from the largest prompt, version 1's instructions cost about 1,550 real tokens. That is more than the 1,230 estimated beforehand, and it narrows the k = 5 margin, which is checked after the freeze.

### Scores (string rule)

| | tp / pred / gold | P | R | F1 |
|---|---|---|---|---|
| Concepts (micro) | 8 / 20 / 27 | 0.400 | 0.296 | **0.340** |
| Relations (micro) | 0 / 4 / 1 | 0.000 | 0.000 | 0.000 |
| Importance | 0 / 0 / 0 | n/a | n/a | agreement 1.000 |

- **Validity:** all 20 windows valid on the first attempt. 0 needed the retry, 0 still invalid.
- **Next to the inter-annotator figure (string rule, ADR-0048 Amendment 3):** model concept F1 0.340 against human agreement 0.240 on the 10 shared windows.

### Missed gold concepts (19)

| Category | Count | Windows (gold label) |
|---|---|---|
| **Known gold/guide mismatch (fixed rule 7)**: a problem or disadvantage of batch learning as its own concept | **7** | 10, 12, 13 (Problem Of Batch Learning); 14, 15, 20 (Problem With Batch Learning; the model labelled "batch learning" in all three, which matched the gold's separate batch-learning concept); 16 (Disadvantages Of Batch Learning) |
| Not named in the window's text: the window continues a concept named earlier. C1 gives no earlier context, so the model cannot identify it | 7 | 8, 9 (Batch Learning); 17, 19 (Hardware Limitation); 18, 21, 22 (Availability) |
| **Named and explained in the window, but missed: the model returned no concepts at all for the window** | **4** | 1 (Production: the window defines it); 16 (Lots Of Data: "big data" that cannot be trained in one go); 19 (Batch Learning: "batch learning fails" here; Availability: "third is availability" and its explanation) |
| Announced topic | 1 | 1 (Types of Machine Learning: announced as the day's topic; the prompt's example 1 treats a topic announced by name as a passing mention) |

The model returned an empty list for 8 windows: 1, 8, 13, 16, 17, 18, 19 and 21.

### Extra model concepts (12)

| Category | Count | Windows (model label) |
|---|---|---|
| Example settings, and process or general words, labelled as concepts | 7 | 9 (static model, recommendation engine); 10 (recommendation engine, machine learning model); 12 (data update, merge, train model) |
| Named in the window, not in the gold | 5 | 4 (online learning); 11 (retraining); 14 (incremental learning); 22 (batch learning, online learning) |

Of the second group, window 22's "batch learning" is a guide-consistent reading: the window says where batch learning fails, which is a problem of it. Window 22 is outside rule 7's windows, so it is counted here. Window 22's "online learning" is announced as the next topic, which is a passing mention.

### Relations (4 predicted, 0 correct; gold has 1)

- **Invented `contrasts_with`:** 3 relations involving concepts not in the gold: windows 4 and 22 (batch learning / online learning) and 14 (batch learning / incremental learning).
- **Wrong direction:** 1 `part_of` that does not hold as stated: window 11, "batch learning part_of retraining".
- **Missed:** the gold's only relation (window 16, Lots Of Data part_of Disadvantages Of Batch Learning), because both concepts were missed.
- **Not meaningful:** with one gold relation, Day 4 relation scores are not meaningful (ADR-0048 Amendment 4).

### Misses under the known mismatch

7 of the 19 missed gold concepts (windows 10, 12, 13, 14, 15, 16, 20) fall under fixed rule 7. They are not named failures for prompt changes. Without them, string-rule recall would be 8/20 = 0.400. That figure is for information only; the reported score stays 0.340.

### Proposed change for version 2 (awaiting approval)

- **Named failure:** "Named and explained in the window, but missed", **4 misses in windows 1, 16 and 19.** In each of these windows the model returned no concepts at all, although the window names the concept and says what it is or what goes wrong with it. In window 1 it is an explicit definition; in windows 16 and 19 the point is made inside a long example scenario.
- **Likely cause:** the "Leave out ... example settings" rule and example 1 (an empty record) make an empty answer the safe choice for windows dominated by a story or an introduction.
- **Change:**
  1. Under CONCEPTS, add: "Check every technical term the window names. If the window defines it, or says how it works, why it is used, or what problem it has, include it, even when most of the window is an example, a story or an introduction. Leave out the example's setting (the company, product or story), not the technical point it makes."
  2. Add one invented example (not from any lecture) of a story-heavy window whose technical point is a named concept with a stated problem, showing the concept included and the story setting left out.
- **No window-specific rules, no gold text:** the invented example will be checked for overlap with the gold windows' text, as version 1 was.

## Version 2 run (18 Oct 2026)

- **Prompt:** `config/prompts/m7_extraction_v2.txt`, sha256 `c7e061fc…4648`. It is version 1 plus only change (a) and (b), approved with conditions.
  - **(a):** added under CONCEPTS, after the leave-out list: "Check every technical term the window names. If the window defines it, or says how it works, why it is used, or what problem it has, include it, even when most of the window is an example, a story or an introduction. Leave out the example's setting (the company, product or story), not the technical point it makes."
  - **(b):** the invented example, added after example 4. It uses a different topic and a different structure from the gold windows: no batch or online learning, no deployment, app, product or news-feed story, no list of limitations:

    > Example 5 (invented): "Think of a student who memorises the answers to last year's papers. On those papers he gets full marks, but in the real exam the questions are new and he fails. A model does the same thing when it overfits: it learns its training examples by heart, even their noise, and then does badly on examples it has never seen."
    > `{"concepts": [{"label": "overfitting", "aliases": []}], "relations": [], "important": false, "cue": null, "is_recap": false}`
    > Most of the window is a story, but it explains overfitting, so overfitting is included. The student and the exam are the story's setting and are left out.
- **Gold-overlap check:** the added text shares no 5-, 4- or 3-word sequence with any gold window's transcript. The whole prompt shares no 5-word sequence, and only the 4-word "types of machine learning" carried over from version 1.
- **Run:** same settings as version 1. Wall time 133.7 s, 61.2 tokens/s, largest prompt 1,970 real tokens, VRAM peak 7,812 MiB (baseline 1,377), 100% GPU. Evidence: `prompt_iteration/v2/`.

### Scores (string rule) against version 1

| | v1 tp / pred / gold | v2 tp / pred / gold | P v1 → v2 | R v1 → v2 | F1 v1 → v2 |
|---|---|---|---|---|---|
| Concepts (micro) | 8 / 20 / 27 | 10 / 22 / 27 | 0.400 → **0.455** (+0.055) | 0.296 → **0.370** (+0.074) | 0.340 → **0.408** (+0.068) |
| Relations (micro) | 0 / 4 / 1 | 0 / 5 / 1 | 0.000 → 0.000 | 0.000 → 0.000 | 0.000 → 0.000 |

- **Validity:** all 20 windows valid on the first attempt. 0 needed the retry, 0 still invalid.
- **Importance:** none predicted, none in the gold.
- **Stop rule:** F1 improved, so the stop rule is not met.

### The 4 named-and-explained misses of version 1

| Window | Gold concept | Version 2 |
|---|---|---|
| 19 | Batch Learning | **recovered** |
| 19 | Availability | **recovered** |
| 16 | Lots Of Data | extracted, but under another name: the model says "big data" for the gold's "Lots Of Data". The string rule does not match them, so it is still a miss under the string rule; it is pending adjudication |
| 1 | Production | **still missed**: the model again returned no concepts for window 1, which defines production |

### Missed gold concepts (17)

| Category | Count | Windows (gold label) |
|---|---|---|
| Known gold/guide mismatch (fixed rule 7) | 7 | 10, 12, 13, 14, 15, 16, 20 (problem or disadvantage of batch learning) |
| Not named in the window's text (C1 gives no earlier context) | 7 | 8, 9 (Batch Learning); 17, 19 (Hardware Limitation); 18, 21, 22 (Availability) |
| Named and explained in the window, still missed | 1 | 1 (Production) |
| Extracted under a different name (string-rule miss, pending adjudication) | 1 | 16 (Lots Of Data, as "big data") |
| Announced topic | 1 | 1 (Types of Machine Learning) |

Neither the known-mismatch misses nor the unnamed-concept misses are named failures for prompt changes (fixed rule 7, and the C1 setting). Without the known-mismatch misses, string-rule recall would be 10/20 = 0.500; that figure is for information only.

### Extra model concepts (12; version 1 had 12)

| Category | Count | Windows (model label) | Version 1 |
|---|---|---|---|
| Example settings and general words | 4 | 9 (static model, recommendation engine); 10 (recommendation engine, machine learning model) | 7 (window 12's data update, merge, train model are gone) |
| **Named in passing as a contrast or a later topic, with a `contrasts_with` built on it** | **3** | 4 (online learning: "the difference between batch and online learning"); 14 (incremental learning: "there is no incremental learning"); 22 (online learning: announced as the next topic) | 3 (4, 14, 22) |
| Not named in the window at all (from the model's own knowledge), with a `contrasts_with` | 1 | 12 (incremental learning) | 0 |
| Named and explained in the window, not in the gold | 1 | 16 (hardware limitation: "the second problem is hardware limitation", then explained) | 1 (11, retraining) |
| Naming variant of a missed gold concept | 1 | 16 (big data, for Lots Of Data) | 0 |
| Guide-consistent (a problem of batch learning stated, the model labels batch learning) | 2 | 12 (inside rule 7's windows; batch learning is not named in window 12, but its procedure is described); 22 (outside rule 7's windows; "batch learning fails" in these scenarios) | 1 (22) |

### Relations (5 predicted, 0 correct; gold has 1)

- **`contrasts_with` to a concept named only in passing, or not named:** 4 relations, in windows 4, 12, 14 and 22.
- **Wrong type:** 1 relation, window 19 "batch learning contrasts_with availability". Availability is a problem of batch learning; no relation type fits, so it should be left out.
- **Missed:** the gold's window 16 relation, because "Lots Of Data" and "Disadvantages Of Batch Learning" were not matched.

### Proposed change for version 3 (awaiting approval)

- **Named failure:** "Named in passing as a contrast or a later topic", **3 extra concepts and 3 invented `contrasts_with` relations in windows 4, 14 and 22.** It is the same in versions 1 and 2. The window explains one concept and names another only as its opposite ("there is no incremental learning", "the difference between batch and online learning") or as the next topic. The model labels the second concept and links the two. The guide counts these as passing mentions, and a relation needs both ends labelled. Window 12 (1 extra, 1 relation) is the same pattern with a concept the window does not name at all, which the prompt already forbids.
- **Likely cause:** examples 2 and 3 show a `contrasts_with` between two concepts. Both are explained there, but the prompt never says that a named contrast alone is not enough.
- **Change (one addition to the leave-out list under CONCEPTS):** "a concept named only as the opposite of, or a comparison to, the concept being explained ("there is no X", "the difference between A and X", "unlike X"), or announced for later, unless the window also explains X itself. If you leave X out, leave out any relation to it." The examples are unchanged; examples 2 and 3 still show the allowed case, where both concepts are explained.
- **Expected effect:** fewer extras (up to 4) and fewer invented relations (up to 4). It should not change the concepts that are explained.
