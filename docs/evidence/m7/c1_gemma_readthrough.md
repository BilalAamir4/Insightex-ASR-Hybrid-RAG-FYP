# M7 C1: read-through of Gemma 4 E4B's output under the frozen prompt (ADR-0048 prompt freeze, ADR-0050)

**What this is.**
- Gemma won C1 (ADR-0050). ADR-0048's prompt-freeze rule then requires the frozen prompt to be re-checked on Gemma: the validity rule, plus a read-through of its output, with no Gemma-specific tuning.
- **Run:** `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/C1/C1-gemma4-e4b/` (18 Oct 2026; prompt v2 `c7e061fc…4648`, harness 7; no new run).
- **Compared with:** Day 4 gold v2.1 (`53248bbb…7d2c`).
- **Done by:** Bilal, on 25 Oct 2026. **Decision: no prompt change.**

## Validity

- 20 of 20 windows valid, all on the first attempt.
- 0 needed the retry, 0 still invalid, 0 valid but empty after the retry.
- 1 relation dropped as dangling (window 11).

## Findings

These patterns are recorded, not fixed. The prompt stays at version 2.

1. **Generic "model" as a concept, in 4 windows (9, 12, 17, 18).**
   - The prompt and the guide list "model" among the general words to leave out unless the window explains it.
   - In windows 17 and 18 the gold concept (Hardware Limitation) is not named in the window, and C1 gives no earlier context. Gemma falls back to the generic word instead of returning nothing.
2. **The example's setting labelled as concepts, in windows 8 and 10:** "recommendation engine", "machine learning model" and "email spam classifier".
   - Prompt v2's change (a) says to leave the example's setting out. On Gemma it did not hold in these windows.
3. **Concepts mentioned only in passing, with invented relations:**
   - "incremental learning" in window 14 and "online learning" in window 22, each with `contrasts_with` batch learning.
   - This is the same pattern qwen3.5 showed in prompt iteration. It was traced to the batch/online and batch/incremental pairings in the examples taken from reserved windows 3 and 5, which are still in prompt v2.
4. **An alias split off as its own concept, in window 6:** "offline learning" appears as a separate concept, with "batch learning example_of offline learning".
   - The prompt's own example 2 gives "offline learning" as an alias of batch learning, so this is both a wrong split and a wrong relation.
5. **A broader "batch learning" than the gold:**
   - Gemma labels "batch learning" in windows 11, 15, 19, 20 and 22, where gold v2/v2.1 has the problem, disadvantage or availability concept.
   - In the v2 pass Bilal removed "batch learning" from 11, 15, 19 and 20 as named but not explained.
   - This is a granularity difference between model and gold, not a language or format fault.
6. **No aliases in any window,** including Urdu-script ones. Gold has only two aliases, so nothing was lost on Day 4. To watch on the held-out lecture.
7. **Empty output in windows 13 and 21.** Gold has Problem Of Batch Learning and Availability there.
8. **All 5 relations Gemma predicted look wrong:**
   - the two passing-mention `contrasts_with` (finding 3);
   - the `example_of` in window 6 (finding 4);
   - two `part_of` links between example-setting concepts in windows 8 and 10 (finding 2).
   - Day 4 relations are not scored (gold v2 has none). This matters for the held-out lecture and for the graph.

**Not a finding:** every label is English, in the guide's lower case. No label is in another language or script. Gemma flagged no window as important, and gold has none.

## Use

These findings describe the frozen configuration. They are inputs to:
- the held-out run of the final configuration, as things to watch;
- Session 3 canonicalisation, where generic labels such as "model" may need a stop list;
- any later prompt freeze, which would be a new freeze, and every comparison already run on the old prompt would be re-run.
