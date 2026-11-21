# m7_verify

Step 2 verification of the production `extract` stage (ADR-0054, Amendment 1) on the **Day 4 dev lecture only**
(`sha256-de27cb67c2acbedebd0c2c7416932b8a`). The held-out lecture is never used. Standalone: HTTP to the API, the
`insightex` CLI as a subprocess, and reads of published files; it imports nothing from `backend/`, never deletes stage
outputs or workspace files (the 90 s cut lecture is removed through `DELETE /api/lectures/{id}`), and prints counts,
equality results and costs only. Results go to `docs/evidence/m7/session3/m7_verify_<UTC stamp>.json`.

Bilal runs it, after `python3 docs/evidence/m7/scripts/check_ollama_frozen.py` prints OK (m7_verify runs that check
first and stops on anything else):

```bash
# 1. the API alone (no worker: m7_verify starts and kills its own for the resume check)
bash ~/insightex/scripts/run_in_env.sh python -m insightex.api &
# 2. the checks
python3 tools/m7_verify/m7_verify.py --api http://127.0.0.1:8000
```

Checks: Ollama frozen; Day 4 extraction with a SIGKILL of the worker once at least 3 windows are stored, then a
restart (exactly the stored valid windows must be reused); the 20 C1 target-window records byte-identical to
`docs/evidence/m7/<Day 4>/C1/C1-gemma4-e4b/extraction.json`; no model resident and the GPU lease free; re-add is a
cache hit; cost; the hold round trip on a 90 s cut (offset `CUT_START_S`, chosen from Day 4 segment timings).

If Day 4 already has a published extraction, the resume check prints `Not run (already extracted)`; that run does not
count for the step 2 exit (ADR-0054 Gate), and m7_verify will not delete the extraction to make it run.
