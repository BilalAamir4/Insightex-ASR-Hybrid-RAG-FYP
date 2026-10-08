# ADR-0025: Media normalisation and workspace layout

Status: Superseded by ADR-0034
Date decided: not recorded; on or before 2026-10-05
Date recorded: 2026-10-08
Module: M2 / M3

## Context

Link ingestion (M3) produced the layout. The local upload path (M2) is still to do and reuses it.

## Decision

Each lecture lives at `<paths.data_dir>/lectures/<lecture_id>/` with:
- `video.mp4` (H.264/AAC for browser playback),
- `audio.wav` (16 kHz mono for ASR),
- `thumbnail.jpg`,
- `manifest.json` (schema v2, with source and decision fields).

A manifest change bumps the schema version.

## Alternatives considered

Not recorded.

## Consequences

Later stages add their outputs to the workspace and record them in the manifest. The upload path (M2) must use the same layout.

## Evidence

`backend/src/insightex/core/manifest.py`; `config/default.yaml` (`ingest.transcode`); `.claude/rules/ingest.md`. The real transcode path was confirmed on an H.264-in-MKV clip (register; no result file in the repo).

## Gate / revisit when

Revisit when the manifest schema changes (new version) or the upload path (M2) finds the layout insufficient.
