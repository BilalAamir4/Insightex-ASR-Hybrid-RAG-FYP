# M7 Day 4: prompt versions re-scored against gold v2 (ADR-0048 Amendment 5, step 4a)

Done on 22 Oct 2026, after gold v2 was frozen (`gold_v2.json` sha256 `19837236e0e56e2368381541ad53d2c11fdc88cde8f224f3d7d439243fa055be`, tag `m7-day4-gold-v2-frozen`; see [m7_day4_gold_v2.md](m7_day4_gold_v2.md)).

**Method:**
- **Inputs:** the saved outputs of prompt-iteration versions 1 to 4 (qwen3.5), from `docs/evidence/m7/sha256-de27cb67c2acbedebd0c2c7416932b8a/prompt_iteration/v1` to `v4`.
- **Scoring:** `extraction.json` scored against gold v2 with `tools/label_concepts` (`score_report`, gold `v2`). The metric is micro concept F1, string rule only, with no adjudication (`adjudications_v2.json` did not exist yet).
- **No new model runs.**
- **What was reported:** only the F1 of each version. The prompt-iteration evidence folders were not changed.

| Version | Prompt sha256 | F1 against gold v2 |
|---|---|---|
| 1 | `d2a50e58…f6a8` | 0.227 |
| 2 | `c7e061fc…4648` | 0.304 |
| 3 | `8857a328…9e9c` | 0.304 |
| 4 | `bff471ab…911e` | 0.294 |

All four runs are valid under ADR-0048 section 7.

**Result:**
- Versions 2 and 3 tie exactly on F1. Under fixed rule 8 ("if versions tie on micro concept F1, the earlier version is frozen"), **version 2 wins**.
- The frozen prompt stays version 2 (`c7e061fc…4648`).
- Amendment 5 step 4b follows: the two existing C1 runs are scored against gold v2 without showing the scores, and a new blind adjudication sheet is made against gold v2.
