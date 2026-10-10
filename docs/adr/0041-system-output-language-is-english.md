# ADR-0041: System output language is English

Status: Accepted
Date decided: 2026-10-10
Date recorded: 2026-10-10
Module: Project

## Context

Lectures are spoken in Hindi, Urdu, English or a mix, and since ADR-0040 the spoken language is chosen per lecture. Whisper transcribes in the spoken language and script (Urdu script with English terms in Latin script for the Day 4 lecture). The project has to decide what language users read, and where transcripts appear.

## Decision

- **Everything users read in the app is English**: answers, citation text, notes, quizzes, flashcards and the concept map.
- **Transcripts stay in the lecture's spoken language and are internal evidence** for search and for the LLM. They are never shown to users: there is no transcript endpoint, viewer or captions. `transcript.vtt` exists only as a developer verification artifact (ADR-0042). The ASR task is always `transcribe`, never `translate` (enforced at config load).
- **A simple-English mode** belongs to the accessibility feature F3, not to a second output language.
- **Other output languages are out of scope**, because:
  - evaluation effort: every output language needs its own judged answers, and the thesis evaluation is already sized for one;
  - LLM writing quality in Hindi and Urdu is unmeasured for the local model (qwen3.5 / Gemma 4 E4B on 8 GB, ADR-0012) and likely weaker than in English;
  - scope: the final-year timeline has no room for a second UI and content language.
- **Open questions, to be measured later and not decided now:**
  - cross-language search with English questions over native-script transcripts: at M5 Test A;
  - how well the LLM reads non-English transcripts: at M7 extraction;
  - what citation text to show next to an English answer: at M11.
- **Per-window English translation** is a candidate component if M5 or M7 show the need. It would be a new stage with its own ADR.

## Alternatives considered

- **Output in the lecture's language.** Multiplies evaluation and depends on unmeasured LLM quality in Hindi and Urdu.
- **Show transcripts to users (captions or a viewer).** Mixed-script, unpunctuated ASR text is a poor reading experience and invites users to quote it as the lecture's words; citations already seek the video, which is the primary evidence.
- **Translate every transcript at ingest.** Costly, adds a lossy step before search, and may not be needed: M5 Test A measures cross-language retrieval first.

## Consequences

- No transcript UI or API is built. Later features read `transcript.json` server-side only.
- Embeddings stay on native-script Whisper text (ADR-0001, unchanged); Roman Urdu is never embedded.
- M5, M7 and M11 must each report the measurement named above before relying on cross-language behaviour.

## Evidence

- ADR-0039 (native-script transcripts, about 40% Latin-script words on Day 4), ADR-0040 (spoken-language choice), ADR-0001 (embedding on native-script text).
- No measurement yet for the open questions; they are gates for M5, M7 and M11.

## Gate / revisit when

Accepted 2026-10-10: the M4 session 2 verification passed (`tools/m4_verify` 12/12, `docs/evidence/m4/`) and the manual checklist was approved. The conditions below were the acceptance gate; the revisit triggers still apply.

Accepted together with ADR-0040 and ADR-0042 when the M4 session 2 manual checklist is approved. Revisit if M5 Test A shows English questions fail to retrieve native-script windows (then per-window translation is evaluated), if M7 shows the LLM cannot read the transcripts, or if the supervisor requires output in Urdu.
