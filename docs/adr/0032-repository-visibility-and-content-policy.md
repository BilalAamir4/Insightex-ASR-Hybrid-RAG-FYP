# ADR-0032: Repository visibility and content policy

Status: Accepted
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: Project

## Context

The repository is public on GitHub. The test lecture's transcript is lecture-derived text. Textbook PDFs are copyrighted.

## Decision

- Public repository: github.com/BilalAamir4/Insightex-ASR-Hybrid-RAG-FYP, tag `import-baseline`.
- Commits carry no AI co-author or attribution. The `scripts/git-hooks/commit-msg` hook enforces this; each clone runs a one-time `git config core.hooksPath scripts/git-hooks`, documented in `README.md`.
- Lecture-derived text (the test-lecture transcript) may stay in the repo for now. It is removed, including from history, before the repo is finalised.
- Textbook PDFs and extracted book text are never committed.

## Alternatives considered

Not recorded.

## Consequences

Removing lecture-derived text from history needs a backup bundle, `git filter-repo`, a force-push of `main` and a re-pushed `import-baseline` tag (M20 plan).
- The textbook chunks committed on 2026-10-07 in `tools/ollama_contract_probe.py` are removed from the tree and added to the pre-finalisation history purge together with the lecture transcript. The probe now reads them from `~/insightex-data/books/ollama_probe_chunks.json`.

## Evidence

`scripts/git-hooks/commit-msg`; `README.md`; `docs/BUILD_ORDER.md` (M20: removal of lecture-derived text, decided 6 Oct 2026).

## Gate / revisit when

Revisit at M20, before the repo is finalised.
