# Insightex features

Feature numbers follow the proposal (F1–F20), which is the single source of truth. Tiers: **Baseline / Optional / Stretch Goal / Exploratory / Cut.** The earlier "Phase 2" tier was removed. The module that builds each feature is listed in `docs/BUILD_ORDER.md`.

When a feature's module starts, split its section into its own file (`Fxx-short-name.md`) if the design grows beyond a few lines.

## Baseline (F1–F15, except F13)

| # | Feature | Notes | Module |
|---|---|---|---|
| F1 | Book reference + page-number Q&A | Page-aware PDF chunking inside the FAISS/hybrid layer. Timestamp↔page fusion is its own retrieval problem, with a ±2-page exit criterion. | M10 |
| F2 | Quiz question → locate in video + book | Reuses the F1 engine entirely. | M10 |
| F3 | Dyslexia font toggle | Framed as an optional comfort preference, not a proven intervention. Cite the null-result evidence proactively. | M12 |
| F4 | "This is important" timestamp flagging | A classification tag on the Ollama concept-extraction pass. It is not keyword/grep matching and not a standalone stage. | M7 |
| F5 | In-app playback with timestamp-linked graph navigation | Range requests via FastAPI (nginx only if needed), H.264/AAC transcode. The product is now a "lecture platform with an AI layer". | M12 |
| F6 | Visual-First XAI | Baseline: a frame grabbed with ffmpeg at the cited timestamp, with no OCR. With the visual pipeline: the nearest scene-change keyframe plus OCR text. | M11 / V1–V3 |
| F7 | Quiz bank, notes, flashcards (student) | | M13 |
| F8 | Prep mode / self-check Q&A (teacher) | Reuses the F1/F2 engine. | M15 |
| F9 | Concept-map viewer (teacher) | | M12 |
| F10 | Within-lecture prerequisite gap check | Uses transcript evidence only when the visual pipeline is off. | M15 |
| F11 | Textbook coverage gap report | Scoped to a chapter-sized page range. | M16 |
| F12 | Importance-flag review tool | Also supplies labelled data for F4 precision/recall. | M14 |
| F14 | Quiz bank and notes, audience-differentiated (teacher) | Same LLM call as F7, with different prompts and a role parameter. | M13 |
| F15 | Revision highlight reel | A compilation of highlights, not a condensed re-lecture. | M16 |

## Added requirement: Link ingestion (done, M3)

The panel required one additional feature: ingesting a lecture from a link instead of a file upload. How far to take it was left to the design.

**Status.** Implemented and verified on 6 Oct 2026 and pushed to GitHub. It includes the engine + CLI, the FastAPI API with one-worker background jobs, and a static HTML ingest/library/player page. All tests and the 9-step browser checklist passed. The real transcode path was confirmed on an H.264-in-MKV clip.

**Design.**
- One path for every source: download the whole file, then play it locally. There is no embedded YouTube player and no audio-only path.
- Sources are YouTube (including the `/live/` URL shape), public Google Drive and direct URLs. YouTube and Drive go through yt-dlp, with Deno in the venv as yt-dlp's JS runtime; gdown was removed.
- Storage is `$INSIGHTEX_DATA/lectures/<lecture_id>/`: `video.mp4`, `audio.wav` (16 kHz mono), `thumbnail.jpg` and `manifest.json` (schema v2, with source and decision fields).
- Limits are 3 h and 4 GB. The user must confirm they have the rights to the video. The server runs on `127.0.0.1:8000`.
- `seekTo(seconds)` is the single player integration point for citations, graph navigation and highlight reels.

**Open items.**
- Storage cleanup and quota are not designed.
- The yt-dlp Drive fallback is untested.
- The SSRF guard has a DNS-rebinding gap.
- HEVC decode has only been tested synthetically.
- The demo-venue network is untested for YouTube downloads.

## Optional

- **Visual pipeline:** scene-change detection + PaddleOCR 3.x (Latin script). It sits behind the `visual.enabled` flag, is time-boxed, and never blocks Baseline.
- **F13: OCR-confidence legibility flag.** Moved to Optional because it needs the visual pipeline.

## Stretch Goal (only if Milestones 1–9 finish early; order F17 → F18 → F19 → F16)

- **F16: Sign-command accessibility channel.**
  - A bounded vocabulary of about 15–20 signs: MediaPipe landmarks feed an LSTM or temporal CNN, which feeds the same intent router as F18.
  - Free-form or continuous ASL is out of scope.
  - The target language is ASL, provisionally, pending supervisor confirmation. If it reverts to PSL, there is no pretrained checkpoint to build on.
- **F17: Voice interaction layer.**
  - Reuses Whisper, so there is no new speech-to-text model.
  - A 3-way classifier routes input: question → RAG, quiz answer → grading, command → navigation.
- **F18: Fully voice-navigated app.**
  - A 3-way intent router: UI command / content navigation / free-form question.
  - The F16 sign channel plugs into this same router.
- **F19: Graph/concept correction tool (teacher).**
  - An editing UI with versioning.
  - It is Stretch rather than Baseline because of the extra engineering.

## Exploratory (no commitment)

- **F16.1: Word-level sign recognition.**
  - A temporal classifier over MediaPipe landmarks.
  - Depends on the ASL decision; PSL would need self-recorded data from scratch.
- **F20: Recap-tag classifier.**
  - A new `is_recap` field on the Ollama extraction pass.
  - There is no committed exit criterion.

## Cut

- Visual content narration: cut, not deferred.
- Sign-language generation (text-to-sign avatar synthesis): cut, not deferred.
- Free-form or continuous sign-language recognition: explicitly out of scope.