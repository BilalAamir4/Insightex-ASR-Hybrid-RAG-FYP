# M7 evidence: extraction arms (ADR-0048)

Nothing here yet: no extraction has run on a real lecture. Session 2a (17 Oct 2026) built the machinery and tested it on synthetic fixtures only.

## Layout

```
docs/evidence/m7/<lecture_id>/<comparison>/<arm>/      written by `insightex extract-eval run --arm <arm>`
    extraction.json    schema v1 document, producer.kind = model; one record per window that came out valid
    run.json           run_version 1: arm, model digest, prompt sha256 (+ context block / translation prompt
                       sha256, and the sha256 of every system message actually sent), options (num_ctx,
                       num_predict, temperature, seed, think), the call plan, per window {valid, attempt_used,
                       dropped_relations, errors per attempt}, totals, cost {wall_s, translation_wall_s,
                       tokens_per_sec, max_prompt_eval_count, ollama_ps_at_largest_prompt, vram}, per-call metrics
    calls.jsonl        every attempt of every call: targets, context, attempt, cache hit, raw reply, metrics, ollama ps
docs/evidence/m7/<lecture_id>/<comparison>/compare_<comparison>.json   label_concepts.py compare
docs/evidence/m7/<lecture_id>/<comparison>/score.json                  label_concepts.py score
```

`cost.measured` is false when any reply came from the reply cache (`<extract.cache_dir>`): then the model was not loaded for those calls and the wall time, tokens/s and VRAM figures do not describe the arm. Report cost only from a run with `cost.measured: true`.

`extraction.json` and `calls.jsonl` hold model output about lecture text (concept labels, aliases): add them to the M20 review of lecture-derived text (ADR-0048 Consequences).
