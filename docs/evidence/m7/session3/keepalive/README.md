# ADR-0056 keep-alive sessions

- `adr0049_case.json`: the ADR-0049 synthetic counterexample frozen as its exact `/api/chat` bodies minus `keep_alive` (k = 1: window 18; k = 3: windows 18, 20, 21 of `docs/measurements/m7/synthetic/day4_shape.json`), built from the code at commit `adad53c` by `../scripts/freeze_adr0049_case.py`. Its sha256 is pinned in `extract.keepalive.synthetic_case_sha256`. Reference (fresh-load) hashes: k = 1 `1d414909…`, k = 3 `e2a7020f…`; ADR-0049's same-session k = 3 replay gave `214e43e6…`.
- `<UTC stamp>/`: one folder per session of `insightex extract-eval keepalive --lecture sha256-de27cb67c2acbedebd0c2c7416932b8a`, void sessions included:
  - `session.json`: outcome (`pass`, `fail`, `void`, `stopped_reference`), served version and digest, settings, the self-test, every check, per-run timings and VRAM, differences, a void session's cause, and `note` (null unless Bilal adds one);
  - `windows.json`: one entry per call (run, part, window or case, position, keep_alive, reply and parsed-result sha256, category, equalities, load_duration, wall time, token counts);
  - `replies.jsonl`: the raw replies, one line per call (Day 4 and the synthetic case only).
- A folder with `replies.jsonl` but no `session.json` (a killed session) blocks the next session until a `cause.md` records why (ADR-0056 decision 4).
