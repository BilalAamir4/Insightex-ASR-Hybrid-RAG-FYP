# ADR-0030: Book page numbering: index and printed label

Status: Proposed
Date decided: not recorded; before 2026-10-08
Date recorded: 2026-10-08
Module: M10

## Context

Book ingest uses PyMuPDF. `page.get_label()` returns the printed page label and can be empty if the PDF defines no labels. The Test B criterion is within +-2 pages, which breaks silently if index and label are confused.

## Decision

Store both the PDF page index and the printed page label for every page.

## Alternatives considered

Storing only the PDF page index or only the label: rejected, because the +-2-page criterion then breaks silently.

## Consequences

Citations show the printed label; the index is kept for locating the page in the PDF.

## Evidence

Label findings for the chosen book (ADR-0029), checked 2026-10-08 with PyMuPDF 1.28.2:
- The PDF defines page labels on all 851 pages; none is empty.
- Index 0 is labelled "Cover", index 1 "BackCover", index 2 onward roman numerals (front matter, index 2 is "i", index 29 is "xxviii").
- From index 30 (label "1") to index 850 (label "821"), the label equals the zero-based index minus 29 on every page.

## Gate / revisit when

Gate (M10 exit): Test B passes within +-2 pages on at least 20 queries, scored against printed labels.
