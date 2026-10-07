# ADR-0029: Textbook for book-grounded features

Status: Accepted
Date decided: not recorded; on or before 2026-10-08
Date recorded: 2026-10-08
Module: M0b

## Context

The choice blocks F1, F2, F11 and Test B. The development lecture is "100 Days of Machine Learning", Day 4, batch vs online learning (11 minutes, Urdu/Hindi + English code-switched).

## Decision

Textbook: Aurélien Géron, *Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow*, 2nd Edition (O'Reilly Media, 2019). The PDF stays outside the repo in `~/insightex-data/books/`. The public demo shows page citations and short snippets only.

## Alternatives considered

- Dive into Deep Learning (D2L, free licence): covers online learning only as a short subsection in its distribution-shift chapter, too thin for a 20-query page test, and it lacks the classical ML that most of the "100 Days of ML" series covers.
- An Introduction to Statistical Learning (ISL, free): does not treat batch vs online learning as a topic.

## Consequences

- The chosen book is copyrighted. Licence note: FILL (not yet supplied).
- Textbook PDFs and extracted book text are never committed (ADR-0032).
- Page numbering rules for citations are in ADR-0030.

## Evidence

Read from the PDF on 2026-10-08 (`tools/textbook_probe/`): title page and copyright page give "SECOND EDITION", "Copyright (c) 2019 Kiwisoft S.A.S.", published by O'Reilly Media, Inc., ISBN 978-1-492-03264-9, September 2019 (releases 2019-09-05, 2019-10-11, 2019-11-22). The PDF has 851 pages, and PDF metadata title is the book title without the edition.

Section "Batch and Online Learning" is in Chapter 1, "The Machine Learning Landscape" (chapter pages: PDF index 30 to 63 zero-based, 31 to 64 one-based, labels 1 to 34). The section spans PDF index 43 to 46 zero-based, 44 to 47 one-based, printed labels 14 to 17.

Coverage of the six lecture topics:

| Topic | Covered | Printed page label |
|---|---|---|
| Batch (offline) learning | yes | 15 |
| Online (incremental) learning | yes | 14 to 17 |
| Mini-batches | yes | 15 |
| Learning rate in online learning | yes | 16 |
| Out-of-core learning | yes | 16 |
| Bad data degrading an online system | yes | 17 |

## Gate / revisit when

Gate: if the supervisor or panel rules a copyrighted book out of the public demo, switch the demo to D2L with a lecture that D2L covers, recorded as a superseding ADR.
