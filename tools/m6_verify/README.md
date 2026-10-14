# M6 verification

`m6_verify.py` checks the M6 exit on the real machine, as far as it can without a browser: ask a question about the Day 4 lecture and get citations that seek to the right moment (ADR-0047), with the ADR-0046 rewrite and every fallback.

Standalone: it never imports from `backend/src/insightex`. It starts its **own** API (port 8012) and worker on an isolated data directory (`~/insightex-data/m6_verify_run`, deleted at the end unless `--keep`), so the real library is untouched, and drives them over HTTP and the CLI. They share the **real** GPU lease and the real Ollama (it loads, unloads and holds them).

```bash
bash ~/insightex/scripts/run_in_env.sh python ~/insightex/tools/m6_verify/m6_verify.py
```

It aborts (exit 2) if a worker runs, the GPU lease is held, Ollama is unreachable, or Ollama has a model loaded. About 5 to 6 minutes (the Day 4 ingest is most of it).

Checks (13): 1 Day 4 ingested through fetch, normalise, asr, index; searchable; `first_segment_start` equals the transcript's. 2 empty, blank, 301-character questions refused with codes; 300 accepted. 3 no model loaded: Roman question still gets citations (`llm_not_loaded`). 4 warm-up loads the model with context 8192. 5 A01, A14, A16, A26, A19r warm: rewrite used and a citation covers the gold span. 6 all 47 questions through `/ask` match the gated G5 hit/miss. 7 rewrite under 2 s. 8 exclusive lease held: `gpu_busy`, results appear, warm-up skipped. 9 1 ms timeout: `timeout` fallback. 10 model unloaded again: A19r still returns citations. 11 API logs hold only count lines (no question or rewrite text). 12 the page has the ask box and the `index` label, `ask.js` is served, Deno tests pass. 13 GPU memory back to the start.

Evidence: `docs/evidence/m6/m6_verify_<time>.json` and `.log` (ids, counts, timings; never question text). The browser part is `docs/evidence/m6/manual_checklist.md`.
