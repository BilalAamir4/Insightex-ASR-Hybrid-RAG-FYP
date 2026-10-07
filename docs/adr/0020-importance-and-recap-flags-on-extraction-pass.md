# ADR-0020: Importance and recap flags ride on the extraction pass

Status: Accepted
Date decided: not recorded; on or before 2026-10-04
Date recorded: 2026-10-08
Module: M7

## Context

Feature 4 is the "this is important" flag. Feature 20 is the recap tag (Exploratory, ADR-0008).

## Decision

Feature 4 is a classification field in the Ollama concept-extraction JSON output. It is not keyword matching and not a separate pipeline stage. Feature 20 is a further field, `is_recap`, on the same pass, with no committed exit criterion. Extraction output is JSON-schema constrained.

## Alternatives considered

- Keyword matching for the importance flag: rejected.
- A separate pipeline stage for the flags: rejected.

## Consequences

- One LLM pass produces concepts and flags, within the ADR-0002 call contract.
- The draft schema field for Feature 4 is `exam_relevant`; `is_recap` is not in the draft yet.

## Evidence

`docs/contracts/extraction.json` (`concepts[]` with `name`, `description`, `exam_relevant`); `docs/BUILD_ORDER.md` (M7).

## Gate / revisit when

Revisit if flag precision/recall (M14) shows the extraction pass cannot carry the flags.
