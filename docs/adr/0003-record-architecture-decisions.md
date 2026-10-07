# ADR-0003: Record architecture decisions

Status: Accepted
Date decided: 2026-10-08
Date recorded: 2026-10-08
Module: M0b

## Context

Project decisions were recorded in chat summaries, reports and `CLAUDE.md`. Two ADRs (0001 and 0002) existed before any template or index. Earlier summaries misreported numbers, so a decision needs one stable file that states the choice, the alternatives and the evidence.

## Decision

- Every project decision is recorded as one ADR in `docs/adr/`, written from `docs/adr/template.md`, named `NNNN-kebab-title.md`.
- A decision that waits on a measurement has status Proposed. Its Gate section names the test and the pass condition.
- An Accepted ADR is never rewritten. A changed decision gets a new ADR that supersedes the old one; only the old ADR's status line changes.
- `docs/adr/README.md` holds the index.
- ADR-0001 (`0001-bge-m3.md`) and ADR-0002 (`0002-ollama-call-contract.md`) predate the template. A later session conforms them to the template without changing their decisions.

## Alternatives considered

- Decisions in `CLAUDE.md` only: the file loads in every session and has a size target of 150 lines, so it cannot carry alternatives and evidence.
- Decisions inside reports in `docs/reports/`: reports record experiments, not the current state of a decision, and give no supersede mechanism.
- One decisions log file: entries cannot be superseded or linked individually.

## Consequences

- Each decision has a stable file name that other documents link to.
- Writing an ADR becomes part of every change that adds or alters a decision.
- Numbers 0001 and 0002 are taken by the pre-template ADRs, so the first template-conformant ADR is 0003.

## Evidence

- `docs/adr/0001-bge-m3.md` and `docs/adr/0002-ollama-call-contract.md` exist without template sections.
- `docs/adr/README.md` index lists four ADRs.

## Gate / revisit when

Revisit when the ADR count makes the index table hard to scan, or when the status values in the README stop covering a real case.
