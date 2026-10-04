# tools/bench_models/loadtimes

**Purpose:** Model load-time benchmark, ext4 cache vs the DrvFS master cache, and a master-vs-runtime cache comparison. Evidence that runtime caches must stay on ext4.

**How to run:** run_loadtimes_benchmark.py (orchestrator; drops the page cache with `wsl -u root`), load_single_model.py (worker), verify_6b_loadtimes.py, compare_caches.py. GPU jobs; one at a time. Do not run casually (drop_caches needs root in WSL).

**Inputs:** Model caches under `$HF_HOME` and `$INSIGHTEX_MODEL_CACHE_MASTER/huggingface`.

**Outputs:** loadtimes_results.json (recorded results, original paths kept as evidence) / console.

**Status:** Kept. verify_6b_loadtimes.py was written but never run. In it, the DrvFS cache path now points at the master HF cache; the original pointed at the LLMs folder.

Standalone tool: it must not import from `backend/`.
