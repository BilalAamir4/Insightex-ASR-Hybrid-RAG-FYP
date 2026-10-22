# M7 Day 4 gold v2 (ADR-0048 Amendments 5 and 6)

Lecture `sha256-de27cb67c2acbedebd0c2c7416932b8a` (Day 4). Gold v2 replaces gold v1 for Day 4 scoring; gold v1 is kept unchanged.

## Files

| | File | sha256 |
|---|---|---|
| Gold v1 (unchanged, tag `m7-day4-gold-frozen`) | `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/gold.json` | `7fcec636170248ed48df8badacf2b40dc1c8edfc96aa073cf8ef90ec58b8a4ff` |
| Gold v2 (tag `m7-day4-gold-v2-frozen`) | `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/gold_v2.json` | `19837236e0e56e2368381541ad53d2c11fdc88cde8f224f3d7d439243fa055be` |
| Relabelling decisions and change log | `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/relabel_v2.json` | see the commit |

- `gold_v2.json` was written by `label_concepts.py relabel-merge`, from `gold.json` and the decisions alone.
- It passes the schema v1 validator, both the backend copy and the tool copy.

## The pass

- **Who and when:** one relabelling pass of all 20 windows by Bilal, on 22 Oct 2026, under the frozen guide.
- **Allowed changes:** keep, remove or rename each gold v1 concept (Amendment 5), and add a concept the window explains or uses substantively (Amendment 6).
- **Reasons:** every removal, rename and addition has a reason in the change log, which has 100 entries.

| | Gold v1 | Gold v2 |
|---|---|---|
| Concepts | 27 | 24: 18 kept (3 renamed), 9 removed, 6 added |
| Relations | 1 (window 16) | 0 |
| Windows with no concepts | 0 | 0 |
| Distinct concept names | 12 (9 ignoring case) | 7 |

The 3 renames all give a concept its one canonical name:
- "Problem With Batch Learning" → "Problem Of Batch Learning" (window 14);
- "Problem of Batch Learning" → "Problem Of Batch Learning" (window 12);
- "batch learning" → "Batch Learning" (window 7).

Concept names in gold v2:

| Name | Windows |
|---|---|
| Availability | 19, 20, 21, 22 |
| Batch Learning | 4, 6, 7, 8, 9, 14 |
| Big Data | 16 |
| Disadvantages Of Batch Learning | 15, 16 |
| Hardware Limitation | 17, 18, 19 |
| Problem Of Batch Learning | 9, 10, 11, 12, 13, 14 |
| Production | 1, 2 |

"Disadvantages Of Batch Learning" is kept as a separate concept from "Problem Of Batch Learning", because windows 15 and 16 explain different scenarios (Bilal's decision).

## Relations

Day 4 gold v2 has no relations:
- The one gold v1 relation (window 16) went with the removal of its concept "Lots Of Data".
- Bilal added none, because Day 4 relation scores were already not meaningful (Amendment 4), and most concept pairs in the multi-concept windows fit none of the four relation types.

**Relation scores on Day 4 are not computed against gold v2. Relations are evaluated on the held-out lecture.**

## Order on record

Commit times are converted from +05:00; the change-log times are UTC from this machine.

| Event | Time (UTC, 22 Oct 2026) |
|---|---|
| Amendment 5 committed (`67b4686`) | 12:58:53 |
| First label change in the pass | 13:01:38 |
| Amendment 6 committed (`919d66a`) | 13:19:45 |
| First addition | 13:23:08 |
| Last change (the three renames) | after 13:47:45 |

What had been seen when the pass was decided is recorded in ADR-0048 Amendment 5, along with the tilt towards qwen3.5.

Step 4a, the prompt versions re-scored against gold v2: [m7_day4_gold_v2_prompt_rescore.md](m7_day4_gold_v2_prompt_rescore.md).
