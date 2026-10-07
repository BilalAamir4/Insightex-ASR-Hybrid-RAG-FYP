# Architecture Decision Records

An ADR records one project decision: the context, the choice, the alternatives rejected, and the evidence. Every project decision has exactly one ADR in this directory, written from [template.md](template.md).

## Status values

| Status | Meaning |
|---|---|
| Proposed | The decision has a planned answer that a named gate (a measurement or test) will confirm or change. The Gate section states the test and its pass condition. |
| Accepted | The decision is in force. |
| Superseded by ADR-XXXX | A later ADR replaced this decision. |
| Deprecated | The decision no longer applies and nothing replaced it. |

## Rules

- An Accepted ADR is never rewritten. A changed decision gets a new ADR that supersedes the old one; only the old ADR's status line changes.
- File names are `NNNN-kebab-title.md`, numbered in order of creation.
- A new decision or a changed decision gets its ADR in the same change that implements it.

## Index

| Number | Title | Status | Module | Note |
|---|---|---|---|---|
| [0001](0001-bge-m3.md) | Embedding model BAAI/bge-m3 with 30-second windows | Accepted | M5 | Predates the template; to be conformed without changing the decision. |
| [0002](0002-ollama-call-contract.md) | Ollama call contract (qwen3.5:latest) | Accepted | M0 | Predates the template; to be conformed without changing the decision. |
| [0003](0003-record-architecture-decisions.md) | Record architecture decisions | Accepted | M0b | |
| [0004](0004-configuration-system.md) | Configuration system | Accepted | M0b | |
