# m7_verify

Step 2 verification of the production `extract` stage (ADR-0054, Amendments 1 and 2) on the **Day 4 dev lecture
only** (`sha256-de27cb67c2acbedebd0c2c7416932b8a`). The held-out lecture `yt-5vqk6HnITko` is never used:
`refuse_held_out()` stops the run before any HTTP path, CLI argument or file path that names it.

Standalone: HTTP to the API, the `insightex` CLI as a subprocess, and reads of published files. It imports nothing from
`backend/` and never deletes stage outputs or workspace files. The 90 s cut lecture is removed through
`DELETE /api/lectures/{id}`. The only file it deletes itself is the temporary cut it wrote.

Results go to `docs/evidence/m7/session3/m7_verify_<UTC stamp>.json`. The file holds counts, statuses, hashes, timings
and equality results only: no labels, aliases, relations, raw replies or transcript text.

## Run instructions (Bilal), in this order

From a WSL shell in `~/insightex`:

1. **Ollama frozen check.** Start the Ollama app by hand, then run:

   ```bash
   python3 docs/evidence/m7/scripts/check_ollama_frozen.py
   ```

   It must print a line starting with `OK:`. On `STOP`, do not continue; tell Bilal. m7_verify runs this check again
   as its first step, before any HTTP call, and stops unless it prints `OK:`.

2. **Start the API alone** (not `scripts/dev_run.sh`, which also starts a worker), in its own terminal:

   ```bash
   bash ~/insightex/scripts/run_in_env.sh python -m insightex.api
   ```

3. **Make sure no worker is running.** m7_verify starts its own worker so it can kill it for the resume check.

   ```bash
   pgrep -af 'insightex(\.cli)? worker'                       # must print nothing
   bash ~/insightex/scripts/run_in_env.sh insightex gpu status   # must say: state: free
   ```

   If a worker is running (for example from `dev_run.sh`), stop it with Ctrl-C in its terminal. A clean stop puts
   a running job back in the queue.

4. **Run m7_verify** in a third terminal:

   ```bash
   python3 tools/m7_verify/m7_verify.py --api http://127.0.0.1:8000
   ```

5. **What a pass looks like.** Every check line starts with `[ok]`:

   ```
   [ok]   ollama frozen: OK: Ollama 0.40.2, gemma4:e4b digest dc35e8d9c606 match ...
   [ok]   day 4 extraction with resume: passed: killed with N windows stored, N reused, M calls after the restart
   [ok]   C1 byte identity: passed: 20 of 20 C1 target windows byte-identical
   [ok]   model unloaded, lease free: passed: no model resident, GPU lease free
   [ok]   re-add is a cache hit: passed: ...
   [info] cost: windows 23, ok ..., failed ..., calls ..., wall ... s, ... tok/s, VRAM peak ... MiB above baseline, ...
      cut: offset 390.0 s, 90.0 s (stream copy|re-encoded), sha256 <64 hex>
   [ok]   hold round trip (90 s cut): passed: held (extract skipped), released, re-added (stages [...]), removed
   [ok]   model unloaded, lease free (after the hold test): passed: ...
   results: docs/evidence/m7/session3/m7_verify_<stamp>.json
   7 of 7 checks passed
   ```

   The exit code is 0. Any `[FAIL]` line, or a final line other than `7 of 7 checks passed`, is a fail.

6. **The resume check must actually run once.** It runs only while Day 4 has no published extraction. The run that
   counts for the step 2 exit (ADR-0054 Gate, Amendment 1 item 9) must therefore be **the first m7_verify run on Day 4
   at the current extract key**. Later runs print
   `day 4 extraction with resume: Not run (already extracted)`, which does not count. m7_verify will not delete the
   extraction to make the check run again. If that first run fails, stop and report it; do not delete files to retry.

## Checks

| Function | Check |
|---|---|
| `check_frozen` | `check_ollama_frozen.py` exits 0 and its last line starts with `OK:`; runs first, before any HTTP call |
| `check_day4_with_resume` | ingest Day 4; SIGKILL the worker once at least `RESUME_MIN_STORED` (3) windows are stored; restart it; exactly the stored valid windows are reused; `.resume/` is gone after publish |
| `check_c1_identity` | the reference has 20 distinct C1 target windows, and each record equals the stage's record for that window byte for byte (canonical JSON) |
| `check_unloaded` | Ollama `/api/ps` shows no model, `insightex gpu status --json` shows the lease free |
| `check_readd_cached` | re-adding Day 4 creates no job, or a job whose stages are all cached |
| `cost_line` | totals and cost from `extract.json` (info, not a pass/fail check) |
| `check_hold_round_trip` | 90 s cut from `CUT_START_S` (390.0 s, chosen from Day 4 segment timings): `--hold-extract` (extract `skipped`, state `held`), release job (state `none`), re-add (extract runs, others cached, state `done`), `DELETE /api/lectures/{id}` then 404 |
