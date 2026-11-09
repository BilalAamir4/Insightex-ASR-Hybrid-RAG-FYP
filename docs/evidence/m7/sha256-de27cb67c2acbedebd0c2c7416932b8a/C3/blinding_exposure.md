# C3 blinding exposure (recorded 9 Nov 2026, before the C3 sheet was opened)

**What happened (as reported by Bilal).** During the C3 arm B run (`C3-batch`, 9 Nov 2026), part of a shell command's output showed raw arm B output for windows 19 to 22 on Bilal's screen. This was before any C3 adjudication decision and before any C3 score.

**What is known and what is not.**
- **The command outputs Claude received** for that run showed only counts, cost and per-call metrics (token counts, wall times, `ollama ps`), with no concepts. So Claude cannot confirm exactly which text was on screen. The exposure is recorded as Bilal reported it.
- **What may have been seen:** arm B's concept labels (and possibly aliases or relations) for windows 19, 20, 21 and 22. Those four windows were all in one batch call, `(18, 19, 20, 21, 22)`.
- **What was not seen:** no arm A output for C3 beyond what C1 and C2 already showed, since arm A is the unblinded C1 Gemma run, and no score or per-window result.

**Effect on the blind sheet.**
- **The item count:** the C3 sheet (`C3-gold_v2_1-20261109T140556Z.json`, 10 entries) has **1 entry in windows 19 to 22**. Bilal was told only that count, not the entry.
- **That entry is not blind.** Bilal may recognise it as arm B's output, so it is not blind as section 4 intends. It is still decided under the same rule: a match to a named gold concept of that window, or no-match.
- **The other 9 entries** are in windows not affected.

**Handling.**
- **No change to the procedure.** The sheet is not rebuilt or reshuffled, and no entry is removed: a decision is still needed for every unmatched concept (section 4).
- **This note is the record.** It is listed as a limitation in the C3 ADR.
- **Where the C3 decision depends on it:** if the decision depends on windows 19 to 22, the ADR says so.
