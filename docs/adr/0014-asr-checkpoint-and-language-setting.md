# ADR-0014: ASR checkpoint and language setting

Status: Superseded by ADR-0039
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M4

## Context

Recorded notes conflict. One says auto-detect beat forced `ur` because forcing dropped lines. Another says `ur` is forced because auto-detect produced Devanagari output.

## Decision

No checkpoint or language is chosen yet. The WER gate decides.

## Alternatives considered

Four configurations: medium and large-v3, each with `ur` forced and with auto-detect. large-v3-turbo is a fifth configuration if time allows.

## Consequences

The winning checkpoint and language, with numbers, become the Accepted replacement ADR.

## Evidence

`docs/BUILD_ORDER.md`, M4 pending decision. `tools/eval_wer/README.md` (WER harness). `docs/MODELS.md` (candidates `Systran/faster-whisper-medium` and `Systran/faster-whisper-large-v3`).

## Gate / revisit when

Gate (M4, run in `tools/eval_wer`):
- Run the four configurations (five with large-v3-turbo).
- Confirm `task=transcribe`, not translate, before computing WER; WER against a translation is invalid.
- Count dropped segments explicitly.
- Enable `word_timestamps=True`.

Pass condition: one configuration is chosen with its WER and dropped-segment count recorded.
