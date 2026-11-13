# M7 held-out lecture: selection record (handoff 4, step 1)

Written 13 Nov 2026, before ingestion. Chosen by Bilal. No transcript, caption or model output for this lecture existed or was read when it was chosen. Rules: ADR-0048 section 2 (held-out lecture), handoff 4 section 5, step 1.

## The lecture

| Field | Value | Source |
|---|---|---|
| Title | Performance Metrics, Accuracy,Precision,Recall And F-Beta Score Explained In Hindi\|Machine Learning | YouTube metadata |
| URL | https://youtu.be/5vqk6HnITko (video id `5vqk6HnITko`) | |
| Channel | Krish Naik Hindi (`@krishnaikhindi`) | YouTube metadata |
| Speaker | Krish Naik | channel |
| Uploaded | 14 May 2022 | YouTube metadata |
| Duration | 1,415 s (23:35) | YouTube metadata |
| Language | metadata `hi`; the only original-language automatic captions are Hindi (`hi-orig`); no uploaded subtitles | YouTube metadata |
| Language as heard | Hindi with English technical terms, like Day 4 | Bilal, from listening to parts of it (not the whole lecture) |
| Expected workspace id | `yt-5vqk6HnITko` (confirmed at ingestion) | |

The metadata was read with `yt-dlp --skip-download --dump-json` on 13 Nov 2026. Nothing was downloaded and the captions were not read.

## Selection rules

| Rule | Result |
|---|---|
| In Hindi, the only tested language (ADR-0039/0040) | **Met.** Ingest with language `hindi` (Whisper `ur`). |
| A different speaker from Day 4 | **Met.** The Day 4 speaker is Nitish Singh (CampusX, *100 Days of Machine Learning*); this is from Bilal and general knowledge, and the repo does not record it. This lecture's speaker is Krish Naik. |
| At least 20 minutes (at least 40 non-empty windows) | **Met on duration, 23:35.** The 30 s grid gives at most 48 windows (47 full and 1 of 5 s). The non-empty count is known only after `asr`/`index`. If it is under 40, the lecture fails this rule and is not used. |
| 25 minutes or more (preferred) | **Not met.** 23:35 is about 1.5 minutes short. Accepted by Bilal. |
| A machine learning topic, so the guide and prompt apply | **Met.** Classification performance metrics, Géron (ADR-0029) chapter 3: confusion matrix, precision, recall, the F1 score. The F-beta score is a generalisation of F1. |
| Preferably not covered by Day 4 | **Met.** Day 4 is batch vs online learning (Géron chapter 1). |

## Why this lecture

- It maps directly onto a textbook chapter, so canonical names under the guide are clear.
- It stands alone (it is not "Part N" of a series), so no concept should depend on an earlier video.
- Its topic is a set of closely related concepts, so the gold set is expected to contain relations. Day 4's gold has one relation, so relations are evaluated only on this lecture. Whether it has enough relations is not known until it is labelled.

## Candidates rejected

| Candidate | Reason |
|---|---|
| "Building AI Teammates", Krish Naik, https://youtu.be/G4zrHUoKgjk | Fails the language rule: about 98% English (Bilal's estimate). Not ingested. |
| Gate Smashers, "Lec-4: Linear Regression", https://youtu.be/zUQr6HAAKp4 | Fails the length rule: 11:00 (about 22 windows). |
| Krish Naik Hindi, Naive Bayes Part 2, https://youtu.be/VIj6xS937E4 (24:36) | Met the rules. Not chosen: Part 2 of a series, and Naive Bayes has only passing mentions in Géron. |
| Krish Naik Hindi, Decision Tree Regression Part 5, https://youtu.be/uHq0I_MDVZU (23:40) | Met the rules (Géron chapter 6). Not chosen: Part 5 of a series. It was the second choice. |

## Consequences for sampling (step 4)

- **Near-census.** About 47 windows are expected, so drawing 40 (ADR-0048 section 3) covers almost the whole lecture: about 7 windows, roughly 15%, are left out. The stratified sample therefore says little about how windows are picked across the timeline. The held-out figures describe this lecture almost completely, and they are still one lecture by one speaker.
- If there are fewer than 40 non-empty windows, the lecture fails (above). N is not lowered to fit.

## Order from here

1. Bilal approves this record, and it is committed **before ingestion**.
2. Ingest with language `hindi` (step 2). Only `normalise`, `asr` and `index` run; no `extract-eval`. Checks report counts and ids only. Nobody, Claude included, reads the transcript or window text until the gold set is merged.
3. Amendment 11 (second annotator), committed before `sample`.
4. `sample --labellers bilal`, then `add-annotator` for Fatima.
