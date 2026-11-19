# M7 held-out lecture: read-through of Gemma 4 E4B's output (final configuration)

**What this is.** A read-through of the single held-out run, like the Day 4 one (`docs/evidence/m7/c1_gemma_readthrough.md`), done after the held-out gold, adjudications and scores were frozen. It records patterns only. **Nothing is changed:** the prompt stays at version 2, and no filter or stop list is applied. Any change suggested by these patterns must not be evaluated on this lecture (see the end).

- **Run:** `docs/evidence/m7/yt-5vqk6HnITko/heldout/final/` (19 Nov 2026; `gemma4:e4b` `dc35e8d9c606`, Ollama 0.40.2, prompt v2 `c7e061fce838`, arm `C4-window`).
- **Gold:** `tools/label_concepts/labels/yt-5vqk6HnITko/gold.json` (`8c92dd27…23f7`), with the frozen adjudications (`94ab8735…9a5258`).
- **Written by:** Claude (Claude Code), 19 Nov 2026, from `extraction.json`, `gold.json` and `score.json`, for Bilal's review. The pattern counts below are from those files; which items are errors under the guide is a reading, not a decision.

## Counts

- **Concepts:** 103 from the model in 40 windows (2.6 per window); 34 in gold (0.85 per window).
- **Most frequent model labels:** precision 15, recall 12, false negative 11, false positive 11, true positive 8, confusion matrix 7, accuracy 4, f beta score 4, true negative 3, spam 3, beta 3, performance matrix 2. Each of the remaining 20 labels appears once.
- **Gold labels:** Focus on precision or recall 12, Confusion Matrix 6, F Beta Score 4, Accuracy 3, Precision 3, Focus on False Positive or False Negative 2, and one each of Performance Metrics, Terminologies Of Confusion Matrix, Imbalanced Dataset and Recall.
- **Empty windows:** model 6, 7, 33, 47; gold 0, 2, 17, 18, 37, 47.
- **Relations:** 24 (part_of 16, contrasts_with 5, example_of 3), in 15 windows; gold has none. One more relation was dropped by the harness in window 42 (the reason was not inspected).
- **Important:** the model flagged 9 windows (9, 14, 15, 17, 20, 25, 32, 40, 43); gold flags 1 (14).
- **Aliases:** 9, in windows 2, 10 and 12. `is_recap` is never true.

## Window by window

**Bold** marks a matched pair (string rule or adjudicated).

| Win | Start | Gold | Model concepts | Model relations | Imp (gold / model) |
|---|---|---|---|---|---|
| 0 | 0:00 | — | logistic regression, binary classification problem statement | logistic regression example_of binary classification problem statement | – / – |
| 1 | 0:30 | **Performance Metrics** | **performance metric** (adj.), confusion matrix, accuracy | confusion matrix example_of performance metric; accuracy example_of performance metric | – / – |
| 2 | 1:00 | — | precision, recall, f beta score, feature (aliases x1, x2), output feature, predicted feature, y | | – / – |
| 3 | 1:30 | **Confusion Matrix** | **confusion matrix** | | – / – |
| 5 | 2:30 | Confusion Matrix | predicted, actual, correct prediction, wrong prediction | predicted contrasts_with actual | – / – |
| 6 | 3:00 | Confusion Matrix | — | | – / – |
| 7 | 3:30 | Confusion Matrix | — | | – / – |
| 8 | 4:00 | **Confusion Matrix** | **confusion matrix** | | – / – |
| 9 | 4:30 | Terminologies Of Confusion Matrix | confusion matrix | | – / **true** |
| 10 | 5:00 | Confusion Matrix | true positive, true negative, false negative, false positive (each alias is a whole Urdu-script sentence) | | – / – |
| 12 | 6:00 | **Accuracy** | **accuracy**, true positive (TP), true negative (TN), false positive (FP), false negative (FN) | each of the four cells part_of accuracy | – / – |
| 13 | 6:30 | **Accuracy** | **accuracy**, confusion matrix | | – / – |
| 14 | 7:00 | **Accuracy** | **accuracy**, precision, recall, f beta score | | **true / true** |
| 15 | 7:30 | **Imbalanced Dataset** | **imbalance data set** (adj.) | | – / **true** |
| 17 | 8:30 | — | precision | | – / **true** |
| 18 | 9:00 | — | precision, recall, confusion matrix, true positive | true positive part_of confusion matrix | – / – |
| 19 | 9:30 | **Precision** | false positive, false negative, **precision**, true positive | true positive part_of precision | – / – |
| 20 | 10:00 | **Precision** | **precision**, false positive, true positive | true positive part_of precision; false positive part_of precision | – / **true** |
| 21 | 10:30 | **Precision** | true positive, false positive, confusion matrix, **precision**, true negative | three cells part_of confusion matrix | – / – |
| 23 | 11:30 | **Recall** | false negative, true positive, precision, **recall**, domain expertise, spam classification | false negative contrasts_with true positive | – / – |
| 24 | 12:00 | Focus on precision or recall | precision, recall, false positive, false negative | | – / – |
| 25 | 12:30 | Focus on precision or recall | spam | | – / **true** |
| 26 | 13:00 | Focus on precision or recall | spam | | – / – |
| 27 | 13:30 | Focus on precision or recall | spam | | – / – |
| 29 | 14:30 | Focus on precision or recall | false positive, precision, hyperparameter tuning | false positive contrasts_with precision | – / – |
| 30 | 15:00 | Focus on precision or recall | recall | | – / – |
| 31 | 15:30 | Focus on precision or recall | blunder | | – / – |
| 32 | 16:00 | Focus on precision or recall | model | | – / **true** |
| 33 | 16:30 | Focus on precision or recall | — | | – / – |
| 35 | 17:30 | Focus on precision or recall | false negative | | – / – |
| 36 | 18:00 | Focus on precision or recall | false negative, recall, tp, ff | recall part_of tp; recall part_of ff | – / – |
| 37 | 18:30 | — | precision, recall, true positive | | – / – |
| 38 | 19:00 | Focus on precision or recall | precision, recall, false positive, false negative, performance matrix | false positive contrasts_with false negative | – / – |
| 39 | 19:30 | **F Beta Score** | **f beta score**, precision, recall | f beta score part_of precision; f beta score part_of recall | – / – |
| 40 | 20:00 | **F Beta Score** | precision, recall, beta, **f beta score** | beta part_of f beta score | – / **true** |
| 42 | 21:00 | F Beta Score | precision, recall | (1 dropped) | – / – |
| 43 | 21:30 | **F Beta Score** | false positive, false negative, performance matrix, **beta** (adj.) | false negative contrasts_with false positive | – / **true** |
| 44 | 22:00 | Focus on False Positive or False Negative | false positive, false negative, harmonic mean, beta | | – / – |
| 45 | 22:30 | Focus on False Positive or False Negative | false negative, false positive | | – / – |
| 47 | 23:30 | — | — | | – / – |

## Patterns

These are recorded, not fixed.

1. **Too-fine terms: the confusion-matrix cells as concepts.**
   - true positive, false positive, false negative and true negative make up 33 of the 103 model concepts (32%), in 16 windows (10, 12, 18–21, 23, 24, 29, 35–38, 43–45; window 36 also has "tp" and "ff").
   - They appear wherever the speaker uses them inside a formula or an example, not only where they are defined.
   - The gold never labels a cell. Window 10 is where they are introduced. Bilal's pre-review label there was the same four cells; he corrected it to Confusion Matrix during the review (before the model ran, logged in `corrections_bilal.json`).
2. **Passing mentions and topic previews.**
   - Window 2 (gold empty) lists precision, recall and f beta score from the speaker's preview. Window 14 adds the same three to accuracy from the preview of what comes next. Window 1 lists confusion matrix and accuracy under performance metric.
   - precision and recall appear in 15 and 12 windows; gold has Precision in 3 and Recall in 1. They are listed in windows about F-beta (39, 40, 42), about the choice between the two (24, 38), and in gold-empty windows (17, 18, 37).
   - Day 4 showed the same pattern (finding 3 there).
3. **Generic words and the example's setting.**
   - "spam" (25, 26, 27), "spam classification" (23), "blunder" (31), "model" (32), "domain expertise" (23), "hyperparameter tuning" (29).
   - Window 0 (gold empty): "logistic regression" and "binary classification problem statement", the example's setting.
   - Window 2: "feature", "output feature", "predicted feature", "y"; window 5: "predicted", "actual", "correct prediction", "wrong prediction". These are the parts of the example table, not named concepts.
   - Generic "model" (32) and the example setting (0) repeat Day 4 findings 1 and 2.
4. **Canonical names and surface forms.**
   - "performance matrix" (38, 43): the speaker's form of "performance metrics", taken as the label, not as an alias of the textbook name.
   - "imbalance data set" (15) and "performance metric" (1): surface forms; both were judged matches in adjudication.
   - "tp" and "ff" (36): an abbreviation and an unclear token as labels, against the guide's full-name rule ("Prefer the full name over an acronym").
   - "beta" (40, 43, 44): the parameter as its own concept; in window 43 Bilal judged it a match for F Beta Score.
   - **Aliases:** in window 10 each alias is a whole Urdu-script sentence ("this cell we call true positive"), not a name. The guide says aliases are other names the speaker said. Window 12's TP/TN/FP/FN are proper aliases. Day 4 had no aliases.
5. **Relations: invented, reversed or of the wrong kind.** Gold has none, so all 24 are unmatched by definition. Read against the relation types:
   - Reversed direction: "f beta score part_of precision / recall" (39), "recall part_of tp / ff" (36).
   - Category errors: "false positive contrasts_with precision" (29), "predicted contrasts_with actual" (5), "logistic regression example_of binary classification problem statement" (0).
   - Formula components as part_of: the cells part_of accuracy (12) or precision (19, 20), "beta part_of f beta score" (40). These are arguable as relations, but not in gold.
   - "cells part_of confusion matrix" (18, 21) and "false positive contrasts_with false negative" (38, 43) are plausible readings that the gold does not record.
6. **Over-flagged importance.**
   - 9 flagged windows against 1 in gold; window 14 is the agreeing one.
   - 7 of the 8 extra flags have a cue built on an emphasis word: "important" (9, 17, 32, 43) or "always remember" (15, 20, 40). The eighth, window 25, has "blunder". The model treats emphasis inside an explanation as a teacher's importance signal. The guide's case B ("important" that is not a teacher signal) covers only part of this.
   - **Cue form:** the guide says the cue is "a short English note, not a copy of the transcript". The cues in windows 9, 14 and 43 copy the transcript (window 9 in mixed Devanagari and Urdu script). The cues in 17, 25 and 32 follow the guide's "Says …" form.
7. **Missed and unnamed concepts.**
   - Windows 6, 7 and 33 are empty, where gold has a concept (Confusion Matrix twice, Focus on precision or recall).
   - The gold's descriptive label "Focus on precision or recall" (12 windows) has no model counterpart. The model gives the components or the example (spam) instead. The string rule cannot match such a label, and in adjudication no model concept was judged to match it.

## Not to be evaluated here

The held-out lecture has now been used once (ADR-0048 section 2). Any change made after seeing this output, such as a stop list, a prompt change or filtering, must not be evaluated on this lecture. It needs new evidence on a fresh lecture.
