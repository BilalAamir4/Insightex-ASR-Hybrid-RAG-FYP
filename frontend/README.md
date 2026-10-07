# frontend

Static HTML/JS served by the FastAPI app (no build step). Contents:

- `index.html`: the ingest, library and player page. It defines `seekTo(seconds)`, the single player integration point (ADR-0026).
- `timestamp.js`: timestamp helpers used by the page.
- `timestamp_test.js`: tests for `timestamp.js`, run with `bash scripts/test_frontend.sh`.

Still to build: ask box and citations (M6).
