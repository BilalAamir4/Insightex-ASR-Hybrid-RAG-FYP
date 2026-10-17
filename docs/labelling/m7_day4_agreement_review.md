# M7 Day 4 agreement review (guide Procedure step 7)

Lecture `sha256-de27cb67c2acbedebd0c2c7416932b8a` (Day 4). Shared windows 2, 4, 8, 9, 11, 13, 16, 17, 19, 21. First annotator Bilal (gold), second annotator Fatima, labelling blind (ADR-0048 Amendment 3). Review dated 18 Oct 2026.

## a. Agreement result

This is the reported human agreement figure. It was computed on the pre-review labels and is not recomputed after the corrections below.

- Pre-review file: `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/bilal_pre_review.json`, sha256 `94f15c4145e8a5da90ba9d40ff8cacf84780e25234426f8efea306ae823b891e`
- Second annotator file: `fatima.json`, sha256 `91fb58b16cda8bba3c153501344c8cf4b5c5e5fc9e6578ededa61c5ff84ab7b0`
- Report: `agreement_bilal_fatima.json` (`agreement --a bilal --b fatima`), string rule only (ADR-0048), 10 windows

| | Precision | Recall | F1 | Matched / Fatima / Bilal |
|---|---|---|---|---|
| Concepts (micro) | 0.273 | 0.214 | 0.240 | 3 / 11 / 14 |
| Relations (micro) | 0.000 | 0.000 | 0.000 | 0 / 1 / 4 |

Under Amendment 3, this figure may be compared only with string-rule-only model concept F1 on the same windows.

## b. Correction log

| Win | Change | Reason |
|---|---|---|
| 2 | Added alias "production environment" | Aliases hold every name the speaker said in the window; said at 88 s |
| 4 | Removed "Online Learning" and its contrasts_with relation | Only named, not explained (passing mention); a relation needs both ends labelled |
| 16 | "Disadvantages Of Batch ML" renamed to "Disadvantages Of Batch Learning"; part_of reversed to Lots Of Data part_of Disadvantages Of Batch Learning | Full name preferred over acronym; part_of(A, B) means A is a component of B, so the relation was inverted |
| 19 | Both part_of relations removed | Inverted, and Availability and Hardware Limitation are not components of batch learning; a missing relation costs less than an invented one |
| 14 | part_of relation removed (Amendment 4) | part_of relation removed (Amendment 4): no relation type fits a concept and its own problem; reversed it is also false |
| 15 | part_of relation removed (Amendment 4) | part_of relation removed (Amendment 4): no relation type fits a concept and its own problem; reversed it is also false |

The first four rows are review corrections on shared windows (Amendment 3). The last two are on non-shared windows under ADR-0048 Amendment 4, which allows only deleting or reversing relations. All six are logged in `corrections_bilal.json`, one entry per correction, each with the labels before and after.

After the Amendment 3 corrections, `bilal.json` had sha256 `5d75ead717bdeb6cca6fd047246cccb3c65e3e9394f21d2898d482df64943369`. A per-window diff against `bilal_pre_review.json` then showed changes on windows 2, 4, 16 and 19 only, exactly as in the table, with every other window and the file header identical. The Amendment 4 corrections then removed only the part_of relations in windows 14 and 15. That save in serve also updated the header field `sample_manifest_sha256` from `c704f9b0…973c` to the current manifest's `50fe40c6…2d72d`, with no label change. The final `bilal.json` has sha256 `72a84060f720c323fe9bfcb80ae2930290e246a0765a288f196a4080189a3fe9`.

## c. Findings

1. **Naming and granularity.** Most of the disagreement comes from naming variants and from granularity: one annotator labelled the section heading, the other labelled the specific point being made. The guide does not settle either case.
2. **Carry-over from the previous window.** In window 4 the second annotator labelled "Types Of Machine Learning", which appears only in window 3. This is a carry-over from the previous window, and it bears on the C4 previous-window context arm (Amendment 2), where the same carry-over could come from the model.
3. **Inverted part_of relations.** The first annotator's part_of relations were inverted. On the shared windows they were corrected under Amendment 3 (reversed in 16, removed in 19). The same inverted relations in non-shared windows 14 and 15 were removed under ADR-0048 Amendment 4. The Day 4 gold now has one relation (window 16), so Day 4 relation scores are not meaningful. Relation extraction is evaluated on the held-out lecture.

## Status

Merged 18 Oct 2026: `tools/label_concepts/labels/sha256-de27cb67c2acbedebd0c2c7416932b8a/gold.json`, sha256 `7fcec636170248ed48df8badacf2b40dc1c8edfc96aa073cf8ef90ec58b8a4ff`, made from the final `bilal.json` alone: 20 windows, 27 concepts, 1 relation (window 16).
