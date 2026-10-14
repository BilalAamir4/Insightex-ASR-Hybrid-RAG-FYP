# frontend

Static HTML/JS served by the FastAPI app (no build step). Contents:

- `index.html`: the ingest, library and player page. Ingest progress is one row per stage, fed by `EventSource` on `/api/jobs/{id}/events` (polling every 2 s if the stream fails); the library has a Delete action. It defines `seekTo(seconds)`, the single player integration point (ADR-0026).
- `timestamp.js`: timestamp helpers used by the page.
- `ask.js`: the ask box's pure logic (question check, citation labels `Moment N: m:ss–m:ss`, the warm-up scheduler: once on open, again at most every 30 s after an answer with `llm_not_loaded`); `ask_test.js` tests it.
- `timestamp_test.js`: tests for `timestamp.js`, run with `bash scripts/test_frontend.sh`.

The player page has the ask box (disabled until the lecture is `searchable`) and up to three citation buttons; pressing one calls `seekTo(seek_s)`. Browser behaviour is checked by hand: `docs/evidence/m6/manual_checklist.md`.
