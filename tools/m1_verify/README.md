# M1 exit-criterion verification

`verify_m1.py` checks the M1 exit criterion on the real machine: the GPU lease is held by a GPU stage, the kernel frees it when the worker is killed with `kill -9`, and a new worker recovers the job with the finished stage cached.

It is standalone. It never imports from `backend/src/insightex`; it drives the `insightex` CLI with subprocess and parses `--json` output. The lease path comes from `insightex gpu status --json`.

## Run

```bash
bash ~/insightex/scripts/run_in_env.sh python tools/m1_verify/verify_m1.py
# options: --cpu-seconds 3  --gpu-seconds 20  --timeout 120  --no-load-model
```

Run it from a WSL shell with Ollama running on Windows. By default it first loads the Ollama model with a short prompt (`num_ctx` 8192), so the run also shows the lease unloading it.

Before starting, it takes the worker lock and the GPU lease without blocking. It aborts (exit 2) if a worker is running or the lease is held. If a check fails midway, it still stops every worker it started.

## Checks

Each prints `PASS`, `FAIL` or `SKIP` with one line of evidence. Exit code 0 only if none fail.

1. The Ollama model is loaded before the run (SKIP if Ollama is unreachable or `--no-load-model`).
2. `jobs enqueue-dummy` returns a job id.
3. A worker subprocess claims the job and `dummy_cpu` reaches `succeeded`.
4. While `dummy_gpu` runs, the script's own non-blocking `flock(LOCK_EX)` on the lease path fails.
5. The model is absent from Ollama's `/api/ps` while `dummy_gpu` holds the lease.
6. After SIGKILL to the worker, the job row still says `running` and the script can take the lease (the kernel released it).
7. A new worker recovers the job: it ends `succeeded`, `dummy_cpu` is `cached`, `attempts` is 2.
8. No `.staging/` entries remain in the workspace.
9. SIGTERM stops the last worker with exit code 0.

## Ollama evidence by hand

While `dummy_gpu` runs (about 20 s), in a second WSL shell:

```bash
curl -s $OLLAMA_BASE_URL/api/ps    # {"models":[]} while the lease is held
```

`ollama ps` is not on the WSL PATH because Ollama runs on Windows; the curl call reads the same endpoint.
