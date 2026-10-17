# M7 Session 2b, part 2: extraction prompt iteration (qwen3.5, Day 4 dev lecture)

Lecture `sha256-de27cb67c2acbedebd0c2c7416932b8a` (Day 4). Gold: `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/gold.json`, sha256 `7fcec636…a4ff`, 20 windows. This is the first stage in which a model reads Day 4. Harness rules: ADR-0048 and ADR-0049.

## Fixed rules (recorded 18 Oct 2026, before version 1 runs)

1. **Version limit:** at most 5 prompt versions.
2. **Every change must be named:** each change after version 1 names a failure seen in the previous run (its category, the count and the window indices) and says how the change addresses it. No exploratory changes.
3. **No gold-window text:** no text from the 20 gold windows goes in the prompt. Examples come only from the reserved windows 0, 3 and 5 (as worked in `docs/labelling/m7_concepts.md`) or are invented. No window-specific rules.
4. **Stop rule:** stop when every window is valid after the one retry and micro concept F1 (string rule) has not improved for two consecutive versions, or after version 5. Freeze the best-scoring version.
5. **Settings:** qwen3.5 only, with the C1 settings: single-window calls, original language, no previous-window context. Gemma does not run in this stage.
6. **Approval:** every version is approved by Bilal before it runs. After each run, the next change is proposed with its named reason and waits for approval.

Each run is scored with `tools/label_concepts` (`score`, string rule) and reported as:
- validity: windows needing the retry, windows still invalid;
- micro concept P/R/F1 and relation P/R/F1;
- failures grouped by category, with window indices.

## Versions

| Version | File | sha256 | Status |
|---|---|---|---|
| 1 | `config/prompts/m7_extraction_v1.txt` | `d2a50e58ac5cb630e69516d59d537d9574de18ec926c187826434bafa696f6a8` (draft) | drafted 18 Oct 2026, awaiting approval |

### Version 1 notes

- **Built from the guide's rules:** the concept definition and substantive test, canonical English labels, aliases copied exactly as written, the four relation types with their directions, importance signals and the cue, and `is_recap` always false.
- **Examples:** the guide's English glosses of reserved windows 0, 3 and 5, plus invented example A (learning rate). The window 5 gloss was reworded slightly ("training uses the whole of your data at once, with no incremental training"), because the guide's wording shared five consecutive words with gold window 14's transcript. After the rewording, no 5-word sequence of the prompt occurs in any gold window's transcript text. One 4-word sequence ("types of machine learning", from the reserved-window glosses) occurs in gold window 1; it is a generic phrase. This was checked by script; only counts were printed, plus the shared phrase from the prompt side.
- **"Unnamed concepts":** the guide lets a labeller use the earlier lecture to identify an unnamed concept. The C1 settings give the model only the window, so version 1 asks it to include an unnamed concept only when the window's own text makes clear which concept it is.
- **Size:** 6,892 characters. The instructions are 1,900 estimated tokens, about 1,230 real tokens on qwen3.5 at the measured 0.647 ratio (not measured). The placeholder used for the k measurements was about 920 real tokens. The k decision is made after the freeze with the real prompt (ADR-0049).
