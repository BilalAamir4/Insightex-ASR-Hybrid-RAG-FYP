#!/usr/bin/env python3
"""M1 exit-criterion check: GPU lease, kill -9 recovery and cache, driven through the insightex CLI.

Standalone: it never imports from backend/src/insightex. Run it through the environment wrapper:

    bash ~/insightex/scripts/run_in_env.sh python tools/m1_verify/verify_m1.py

See README.md in this folder.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

RESULTS: list[tuple[str, bool | None, str]] = []  # (name, passed or None for skipped, evidence)
WORKERS: list[subprocess.Popen] = []
CREATED: dict[str, str] = {}  # job_id and workspace of the dummy job this run enqueued


def record(name: str, ok: bool | None, evidence: str) -> bool:
    RESULTS.append((name, ok, evidence))
    label = "SKIP" if ok is None else "PASS" if ok else "FAIL"
    print(f"{label}  {name}: {evidence}", flush=True)
    return bool(ok)


class Abort(Exception):
    pass


def cli(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, "-m", "insightex.cli", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise Abort(f"insightex {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()[-300:]}")
    return proc


def cli_json(args: list[str]) -> dict:
    return json.loads(cli([*args, "--json"]).stdout)


def start_worker() -> subprocess.Popen:
    p = subprocess.Popen([sys.executable, "-m", "insightex.cli", "worker"], stderr=subprocess.DEVNULL)
    WORKERS.append(p)
    return p


def stop_workers() -> list[int | None]:
    codes = []
    for p in WORKERS:
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        codes.append(p.returncode)
    return codes


def wait_for(predicate, timeout: float, what: str, interval: float = 0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise Abort(f"timed out after {timeout:g}s waiting for {what}")


def try_lock(path: Path) -> bool:
    """True if a non-blocking exclusive flock succeeded (and was released again)."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    finally:
        os.close(fd)


def ollama_json(base: str, path: str, body: dict | None = None, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def model_loaded(base: str, model: str) -> bool:
    return any(m.get("name") == model for m in ollama_json(base, "/api/ps", timeout=10).get("models", []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cpu-seconds", type=float, default=3)
    ap.add_argument("--gpu-seconds", type=float, default=20)
    ap.add_argument("--timeout", type=float, default=120, help="seconds to wait for each step")
    ap.add_argument("--out", type=Path, help="JSON result file (default: results/verify_m1_<UTC timestamp>.json here)")
    ap.add_argument("--keep-workspace", action="store_true", help="do not delete the dummy workspace afterwards")
    ap.add_argument("--no-load-model", action="store_true", help="do not load the Ollama model before the run")
    args = ap.parse_args()

    status = cli_json(["gpu", "status"])
    lease_path, run_dir = Path(status["lease_path"]), Path(status["run_dir"])
    workspaces_dir = Path(status["workspaces_dir"])
    ollama_base, ollama_model = status["ollama_base_url"], status["ollama_model"]
    print(f"lease_path={lease_path}\nworkspaces_dir={workspaces_dir}\nollama={ollama_base} model={ollama_model}")

    if not try_lock(run_dir / "worker.lock"):
        print("ABORT: a worker is already running (worker.lock is held). Stop it and rerun.", file=sys.stderr)
        return 2
    if not try_lock(lease_path):
        print("ABORT: the GPU lease is held by another process. Rerun when it is free.", file=sys.stderr)
        return 2

    try:
        try:
            run_checks(args, lease_path, workspaces_dir, ollama_base, ollama_model)
        except Abort as exc:
            record("run", False, str(exc))
        finally:
            stop_workers()
        # The last worker's exit code is the clean-stop check; earlier workers were killed or already stopped.
        if WORKERS:
            record("worker stops on SIGTERM with exit 0", WORKERS[-1].returncode == 0, f"exit code {WORKERS[-1].returncode}")
        write_results(args.out)
    finally:
        if not args.keep_workspace:
            cleanup_workspace()
            write_results(args.out)  # rewrite so the JSON also holds the cleanup check
    failed = [n for n, ok, _ in RESULTS if ok is False]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    print(f"results written to {RESULT_PATH[0]}")
    return 1 if failed else 0


RESULT_PATH: list[Path] = []


def write_results(out: Path | None) -> None:
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [n for n, ok, _ in RESULTS if ok is False]
    now = datetime.now(UTC)
    if RESULT_PATH:
        out = RESULT_PATH[0]
    elif out is None:
        out = Path(__file__).resolve().parent / "results" / f"verify_m1_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    repo = Path(__file__).resolve().parents[2]
    git = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    doc = {
        "timestamp": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "git_commit": git.stdout.strip() or None,
        "checks": [
            {"name": n, "status": "skip" if ok is None else "pass" if ok else "fail", "evidence": e}
            for n, ok, e in RESULTS
        ],
        "passed": passed,
        "total": len(RESULTS),
        "all_passed": not failed,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    RESULT_PATH[:] = [out]


def cleanup_workspace() -> None:
    """Delete the dummy workspace this run created with `insightex cache delete` and record the outcome."""
    name = "dummy workspace deleted with cache delete"
    workspace = CREATED.get("workspace")
    if not workspace:
        record(name, None, "no workspace was created")
        return
    try:
        job_id = CREATED["job_id"]
        if cli_json(["jobs", "show", job_id])["status"] in ("queued", "running"):
            cli(["jobs", "cancel", job_id], check=False)  # an unfinished job would make delete refuse
    except Abort:
        pass
    proc = cli(["cache", "delete", workspace], check=False)
    detail = proc.stdout.strip() or proc.stderr.strip()
    record(name, proc.returncode == 0, f"cache delete {workspace}: exit {proc.returncode}, {detail}")


def run_checks(args, lease_path: Path, workspaces_dir: Path, ollama_base: str, ollama_model: str) -> None:
    loaded_before: bool | None = None
    if not args.no_load_model:
        try:
            ollama_json(ollama_base, "/api/generate", {
                "model": ollama_model, "prompt": "Reply with the word ok.", "stream": False, "think": False,
                "keep_alive": "10m", "options": {"num_ctx": 8192, "num_predict": 4, "temperature": 0},
            }, timeout=300)
            loaded_before = model_loaded(ollama_base, ollama_model)
            record("Ollama model loaded before the run", loaded_before, f"{ollama_model} in /api/ps: {loaded_before}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            record("Ollama model loaded before the run", None, f"Ollama unreachable ({exc}); unload evidence skipped")

    job_id = cli(["jobs", "enqueue-dummy", "--cpu-seconds", str(args.cpu_seconds), "--gpu-seconds", str(args.gpu_seconds)]).stdout.strip()
    CREATED["job_id"] = job_id
    CREATED["workspace"] = cli_json(["jobs", "show", job_id])["workspace_id"]
    record("enqueue-dummy returns a job id", len(job_id) == 32, f"job {job_id}")

    def job() -> dict:
        return cli_json(["jobs", "show", job_id])

    first = start_worker()
    wait_for(lambda: job()["stages"][0]["status"] == "succeeded", args.timeout, "dummy_cpu to succeed")
    j = job()
    record("worker claims the job; dummy_cpu succeeded", j["worker_pid"] == first.pid, f"worker pid {j['worker_pid']}, dummy_cpu={j['stages'][0]['status']}")

    wait_for(lambda: job()["stages"][1]["status"] == "running", args.timeout, "dummy_gpu to run")
    got = try_lock(lease_path)
    holder = cli_json(["gpu", "status"])
    record("lease is held while dummy_gpu runs", not got, f"non-blocking flock(LOCK_EX) {'succeeded' if got else 'failed'}; gpu status: {holder['state']}, holder {holder['holder']}")
    if loaded_before is not None:
        try:
            still = model_loaded(ollama_base, ollama_model)
            record("Ollama model unloaded while dummy_gpu holds the lease", not still, f"{ollama_model} in /api/ps: {still}")
        except (urllib.error.URLError, OSError) as exc:
            record("Ollama model unloaded while dummy_gpu holds the lease", False, f"Ollama became unreachable: {exc}")

    first.send_signal(signal.SIGKILL)
    first.wait(timeout=10)
    row_status = job()["status"]
    freed = try_lock(lease_path)
    record("after SIGKILL: job row still running, lease free", row_status == "running" and freed, f"job status {row_status}; flock acquired and released: {freed}")

    start_worker()
    wait_for(lambda: job()["status"] in ("succeeded", "failed", "cancelled"), args.timeout + args.gpu_seconds, "recovered job to finish")
    j = job()
    stages = {s["name"]: s["status"] for s in j["stages"]}
    record(
        "recovered job succeeded with dummy_cpu cached, attempts 2",
        j["status"] == "succeeded" and stages.get("dummy_cpu") == "cached" and j["attempts"] == 2,
        f"status {j['status']}, stages {stages}, attempts {j['attempts']}" + (f", error {j['error']}" if j["error"] else ""),
    )

    leftovers = [str(p) for p in (workspaces_dir / j["workspace_id"] / ".staging").glob("*")] if (workspaces_dir / j["workspace_id"]).exists() else []
    record("no .staging entries remain", not leftovers, f"{len(leftovers)} entries in {workspaces_dir / j['workspace_id'] / '.staging'}")


if __name__ == "__main__":
    sys.exit(main())
