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
| 1 | `config/prompts/m7_extraction_v1.txt` | `d2a50e58ac5cb630e69516d59d537d9574de18ec926c187826434bafa696f6a8` | approved as drafted, 18 Oct 2026 |

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
