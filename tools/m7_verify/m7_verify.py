"""M7 Session 3 step 2 verification of the production `extract` stage on the Day 4 dev lecture (ADR-0054, Amendment 1).

Standalone: talks to the API over HTTP, runs the `insightex` CLI as a subprocess, reads published files from the
workspace. It never imports `backend/`, never deletes stage outputs or workspace files, and never uses the held-out
lecture. It prints counts, equality results and costs only, never model output.

Run it only after `python3 docs/evidence/m7/scripts/check_ollama_frozen.py` prints OK (it runs that check first and
stops otherwise), with the API running and NO worker running (m7_verify starts its own worker so it can kill it for
the resume check):

    bash ~/insightex/scripts/run_in_env.sh python -m insightex.api &      # the API alone, not dev_run.sh
    python3 tools/m7_verify/m7_verify.py [--api http://127.0.0.1:8000]

Checks, in order:
  1. Ollama frozen (check_ollama_frozen.py prints OK).
  2. Day 4 extraction with a resume: ingest the Day 4 file, kill the worker (SIGKILL) once at least
     RESUME_MIN_STORED windows are in the resume store, restart it; the job must finish with exactly the stored
     windows reused. "Not run (already extracted)" when Day 4 already has a published extraction (that does not count
     for the step 2 exit, ADR-0054 Gate).
  3. The records of the 20 C1 target windows are byte-identical to the C1 Gemma run's extraction.json.
  4. Ollama has no model resident and the GPU lease is free after the job.
  5. Re-adding Day 4 is a cache hit (no job, or a job whose stages are all cached).
  6. Cost of the extraction (from extract.json).
  7. Hold round trip on a 90 s cut of the Day 4 video: ingest with --hold-extract (extract skipped, state held),
     release (state none), re-add (extract runs, other stages cached, state done), remove through
     DELETE /api/lectures/{id} (a failed removal is a failed check).
Exit 0 when every check that ran passed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "run_in_env.sh"
FROZEN_CHECK = REPO / "docs" / "evidence" / "m7" / "scripts" / "check_ollama_frozen.py"
DAY4_ID = "sha256-de27cb67c2acbedebd0c2c7416932b8a"
HELD_OUT_ID = "yt-5vqk6HnITko"  # never touched; checked only to refuse a mix-up
C1_EXTRACTION = REPO / "docs" / "evidence" / "m7" / DAY4_ID / "C1" / "C1-gemma4-e4b" / "extraction.json"
DAY4_LANGUAGE = "hindi"
OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
# Start of the 90 s hold-test cut: Day 4 segments from 389.64 s on have gaps <= 0.56 s and no_speech_prob <= 0.3
# for 90 s (chosen from the transcript's segment timings only, 2026-11-21)
CUT_START_S = 390.0
CUT_LENGTH_S = 90.0
RESUME_MIN_STORED = 3  # windows that must be in the resume store before the worker is killed
POLL_S = 1.0
JOB_TIMEOUT_S = 3 * 3600  # the whole Day 4 pipeline at most (extraction alone measured ~ minutes in M7)


class CheckFailed(Exception):
    pass


# -- helpers -------------------------------------------------------------------------------------------------------


def env_value(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    out = subprocess.run(["bash", str(WRAPPER), "printenv", name], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def cli(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(WRAPPER), "python", "-m", "insightex.cli", *args], capture_output=True,
                          text=True, check=check)


def http(api: str, method: str, path: str) -> tuple[int, dict | None]:
    req = urllib.request.Request(api.rstrip("/") + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body) if body else None
        except ValueError:
            return e.code, None


def job(api: str, job_id: str) -> dict:
    status, doc = http(api, "GET", f"/api/jobs/{job_id}")
    if status != 200 or doc is None:
        raise CheckFailed(f"GET /api/jobs/{job_id} gave HTTP {status}")
    return doc


def wait_job(api: str, job_id: str, timeout_s: float = JOB_TIMEOUT_S) -> dict:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        doc = job(api, job_id)
        if doc["status"] in ("succeeded", "failed", "cancelled"):
            return doc
        time.sleep(POLL_S)
    raise CheckFailed(f"job {job_id} did not finish within {timeout_s:g} s")


def stage(doc: dict, name: str) -> dict:
    return next(s for s in doc["stages"] if s["name"] == name)


def first_line(text: str | None) -> str:
    return (text or "").splitlines()[0] if text else ""


def manifest(data: Path, ws: str) -> dict:
    try:
        return json.loads((data / "workspaces" / ws / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"stages": {}}


def extract_dir(data: Path, ws: str) -> Path | None:
    entry = manifest(data, ws)["stages"].get("extract")
    if not entry:
        return None
    d = data / "workspaces" / ws / "stages" / "extract" / entry["key"]
    return d if d.is_dir() else None


def stored_windows(data: Path, ws: str) -> dict[int, str]:
    """Window index -> stored status of every complete entry in the resume store (temporary files are ignored)."""
    out = {}
    for p in glob.glob(str(data / "workspaces" / ws / ".resume" / "extract-*" / "w*.json")):
        name = Path(p).name
        if name[1:-5].isdigit():
            try:
                out[int(name[1:-5])] = json.loads(Path(p).read_text(encoding="utf-8")).get("status")
            except (OSError, ValueError):
                continue
    return out


def ingest_file(path: Path, *flags: str) -> dict:
    out = cli("ingest-file", str(path), "--confirm-rights", "--language", DAY4_LANGUAGE, *flags)
    try:
        return {"exit": out.returncode, **json.loads(out.stdout.strip().splitlines()[-1])}
    except (ValueError, IndexError):
        raise CheckFailed(f"ingest-file printed no JSON (exit {out.returncode}): {first_line(out.stderr)}") from None


class Worker:
    """Our own `insightex worker`, in its own process group so it can be killed with SIGKILL."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(["bash", str(WRAPPER), "python", "-m", "insightex.cli", "worker"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                     start_new_session=True)
        time.sleep(3.0)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise CheckFailed("the worker did not start (is another worker running? run the API alone, not "
                              f"dev_run.sh): {first_line(err[-500:])}")

    def kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.kill()


# -- checks --------------------------------------------------------------------------------------------------------


def check_frozen() -> str:
    out = subprocess.run([sys.executable, str(FROZEN_CHECK)], capture_output=True, text=True, check=False)
    last = first_line(out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr)
    if out.returncode != 0:
        raise CheckFailed(f"check_ollama_frozen.py: {last}")
    return last


def check_day4_with_resume(api: str, data: Path, worker: Worker, day4: Path) -> tuple[str, dict | None]:
    if extract_dir(data, DAY4_ID) is not None:
        return "Not run (already extracted)", None
    result = ingest_file(day4)
    if result.get("exit") != 0 or not result.get("job_id"):
        raise CheckFailed(f"ingest-file Day 4: exit {result.get('exit')}, job {result.get('job_id')}")
    job_id = result["job_id"]
    end = time.monotonic() + JOB_TIMEOUT_S
    while True:
        doc = job(api, job_id)
        if doc["status"] in ("succeeded", "failed", "cancelled"):
            raise CheckFailed(f"the Day 4 job ended ({doc['status']}) before the kill point; "
                              f"{first_line(doc.get('error'))}")
        if stage(doc, "extract")["status"] == "running" and len(stored_windows(data, DAY4_ID)) >= RESUME_MIN_STORED:
            break
        if time.monotonic() > end:
            raise CheckFailed("the extract stage did not reach the kill point in time")
        time.sleep(0.2)
    worker.kill()
    stored = stored_windows(data, DAY4_ID)
    worker.start()
    doc = wait_job(api, job_id)
    if doc["status"] != "succeeded":
        raise CheckFailed(f"the resumed Day 4 job {doc['status']}: {first_line(doc.get('error'))}")
    d = extract_dir(data, DAY4_ID)
    if d is None:
        raise CheckFailed("no published extraction after the resumed job")
    meta = json.loads((d / "extract.json").read_text(encoding="utf-8"))
    reused = {w["window_index"] for w in meta["windows"] if w.get("reused_from_store")}
    stored_valid = {i for i, st in stored.items() if st in ("ok", "ok_after_retry")}  # failed ones are called again
    if reused != stored_valid or not reused:
        raise CheckFailed(f"resume: {len(stored)} windows stored at the kill ({len(stored_valid)} valid), "
                          f"{len(reused)} reused")
    if (data / "workspaces" / DAY4_ID / ".resume").exists():
        raise CheckFailed("the resume store was not deleted after publish")
    text = (f"passed: killed with {len(stored)} windows stored, {len(reused)} reused, {meta['totals']['calls']} "
            "calls after the restart")
    return text, meta


def check_c1_identity(data: Path) -> str:
    d = extract_dir(data, DAY4_ID)
    if d is None:
        raise CheckFailed("Day 4 has no published extraction")
    ours = {r["window"]["window_index"]: r for r in json.loads((d / "extraction.json").read_text("utf-8"))["windows"]}
    ref = json.loads(C1_EXTRACTION.read_text(encoding="utf-8"))["windows"]
    canon = lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    same = [r["window"]["window_index"] for r in ref
            if r["window"]["window_index"] in ours and canon(ours[r["window"]["window_index"]]) == canon(r)]
    differ = sorted(r["window"]["window_index"] for r in ref if r["window"]["window_index"] not in same)
    if differ:
        raise CheckFailed(f"{len(same)} of {len(ref)} C1 target windows identical; differing window indices {differ}")
    return f"passed: {len(same)} of {len(ref)} C1 target windows byte-identical"


def check_unloaded() -> str:
    with urllib.request.urlopen(OLLAMA.rstrip("/") + "/api/ps", timeout=10) as r:
        resident = [m.get("name") for m in json.load(r).get("models", [])]
    status = cli("gpu", "status", "--json")
    try:
        lease = json.loads(status.stdout)["state"]
    except (ValueError, KeyError):
        raise CheckFailed(f"gpu status gave no JSON: {first_line(status.stderr)}") from None
    if resident or lease != "free":
        raise CheckFailed(f"{len(resident)} model(s) resident in Ollama, GPU lease {lease}")
    return "passed: no model resident, GPU lease free"


def check_readd_cached(api: str, day4: Path) -> str:
    result = ingest_file(day4)
    if result.get("job_id") is None and result.get("deduplicated"):
        return "passed: re-add is a no-op (every stage current)"
    if result.get("job_id"):
        doc = wait_job(api, result["job_id"])
        statuses = [s["status"] for s in doc["stages"]]
        if doc["status"] == "succeeded" and all(s == "cached" for s in statuses[1:]):
            return f"passed: re-add job with stages {statuses}"
        raise CheckFailed(f"re-add job {doc['status']} with stages {statuses}")
    raise CheckFailed(f"re-add gave exit {result.get('exit')} and no job")


def cost_line(meta: dict | None, data: Path) -> str:
    if meta is None:
        d = extract_dir(data, DAY4_ID)
        meta = json.loads((d / "extract.json").read_text(encoding="utf-8")) if d else None
    if meta is None:
        return "no extraction"
    c, t = meta["cost"], meta["totals"]
    vram = (c.get("vram") or {}).get("peak_above_baseline_mib")
    return (f"windows {t['windows']}, ok {t['ok']}, ok_after_retry {t['ok_after_retry']}, failed {t['failed']}, "
            f"calls {t['calls']}, reused {t['reused_from_store']}; wall {c['wall_s']} s, {c['tokens_per_sec']} tok/s, "
            f"VRAM peak {vram} MiB above baseline, largest prompt {c['max_prompt_eval_count']} tokens "
            "(the last run only: a resumed run's wall time covers the restart)")


def make_cut(day4: Path, out: Path) -> str:
    def ffmpeg(*args: str) -> None:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

    ffmpeg("-ss", f"{CUT_START_S}", "-t", f"{CUT_LENGTH_S}", "-i", str(day4), "-c", "copy", str(out))
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of",
                            "json", str(out)], capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    kinds = sorted(s["codec_type"] for s in info.get("streams", []))
    duration = float(info.get("format", {}).get("duration", 0))
    if kinds != ["audio", "video"] or abs(duration - CUT_LENGTH_S) > 5:
        ffmpeg("-ss", f"{CUT_START_S}", "-t", f"{CUT_LENGTH_S}", "-i", str(day4), "-c:v", "libx264", "-preset", "fast",
               "-c:a", "aac", str(out))
        return "re-encoded"
    return "stream copy"


def lecture_state(api: str, ws: str) -> str | None:
    status, doc = http(api, "GET", f"/api/lectures/{ws}")
    return (doc.get("extraction") or {}).get("state") if status == 200 and doc else None


def check_hold_round_trip(api: str, day4: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="m7_verify_") as tmp:
        cut = Path(tmp) / "day4_cut_90s.mp4"
        how = make_cut(day4, cut)
        sha = hashlib.sha256(cut.read_bytes()).hexdigest()
        ws = f"sha256-{sha[:32]}"
        print(f"   cut: offset {CUT_START_S} s, {CUT_LENGTH_S} s ({how}), sha256 {sha}")
        held = ingest_file(cut, "--hold-extract", "--wait")
        if held.get("exit") != 0 or held.get("status") != "succeeded":
            raise CheckFailed(f"held ingest: exit {held.get('exit')}, status {held.get('status')}, "
                              f"{held.get('code') or held.get('error')}")
        doc = job(api, held["job_id"])
        if stage(doc, "extract")["status"] != "skipped" or lecture_state(api, ws) != "held":
            raise CheckFailed(f"held ingest: extract {stage(doc, 'extract')['status']}, state {lecture_state(api, ws)}")
        rel = cli("extract-hold", "release", ws)
        if rel.returncode != 0:
            raise CheckFailed(f"release: exit {rel.returncode}: {first_line(rel.stderr)}")
        rel_doc = wait_job(api, json.loads(rel.stdout)["job_id"], timeout_s=300)
        if rel_doc["status"] != "succeeded" or lecture_state(api, ws) != "none":
            raise CheckFailed(f"release job {rel_doc['status']}, state {lecture_state(api, ws)}")
        again = ingest_file(cut, "--wait")
        if again.get("status") != "succeeded":
            raise CheckFailed(f"re-add after release: {again.get('status')} {again.get('code') or ''}")
        statuses = [s["status"] for s in job(api, again["job_id"])["stages"]]
        if statuses[-1] != "succeeded" or any(s != "cached" for s in statuses[1:-1]) or lecture_state(api, ws) != "done":
            raise CheckFailed(f"re-add after release: stages {statuses}, state {lecture_state(api, ws)}")
        status, _ = http(api, "DELETE", f"/api/lectures/{ws}")
        gone, _ = http(api, "GET", f"/api/lectures/{ws}")
        if status != 204 or gone != 404:
            raise CheckFailed(f"removal through DELETE /api/lectures/{ws}: HTTP {status}, then GET {gone}")
    return f"passed: held (extract skipped), released, re-added (stages {statuses}), removed"


# -- main ----------------------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    data = Path(env_value("INSIGHTEX_DATA"))
    day4 = data / "eval" / "day04_batch_vs_online" / "raw" / "lecture_test.mp4"
    if hashlib.sha256(day4.read_bytes()).hexdigest()[:32] != DAY4_ID[len("sha256-"):]:
        print(f"STOP: {day4} is not the Day 4 lecture")
        return 1
    assert HELD_OUT_ID not in str(day4)
    status, _ = http(args.api, "GET", "/api/lectures")
    if status != 200:
        print(f"STOP: the API at {args.api} is not answering (HTTP {status})")
        return 1

    results: list[tuple[str, str, bool]] = []

    def run(name: str, fn, *a):
        try:
            text = fn(*a)
            out = text[0] if isinstance(text, tuple) else text
            results.append((name, out, True))
            print(f"[ok]   {name}: {out}")
            return text
        except (CheckFailed, subprocess.CalledProcessError, OSError, KeyError, ValueError) as e:
            results.append((name, str(e), False))
            print(f"[FAIL] {name}: {e}")
            return None

    if run("ollama frozen", check_frozen) is None:
        print("STOP: Ollama does not match the frozen configuration; do not run, tell Bilal.")
        return 1
    worker = Worker()
    try:
        worker.start()
        day4_result = run("day 4 extraction with resume", check_day4_with_resume, args.api, data, worker, day4)
        meta = day4_result[1] if isinstance(day4_result, tuple) else None
        run("C1 byte identity", check_c1_identity, data)
        run("model unloaded, lease free", check_unloaded)
        run("re-add is a cache hit", check_readd_cached, args.api, day4)
        print(f"[info] cost: {cost_line(meta, data)}")
        run("hold round trip (90 s cut)", check_hold_round_trip, args.api, day4)
        run("model unloaded, lease free (after the hold test)", check_unloaded)
    finally:
        worker.stop()
    failed = [n for n, _, ok in results if not ok]
    out_dir = REPO / "docs" / "evidence" / "m7" / "session3"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    report = {"run_at": stamp, "lecture_id": DAY4_ID, "cut_start_s": CUT_START_S, "cut_length_s": CUT_LENGTH_S,
              "checks": [{"name": n, "result": r, "passed": ok} for n, r, ok in results],
              "cost": cost_line(meta, data)}
    (out_dir / f"m7_verify_{stamp}.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"results: {out_dir / f'm7_verify_{stamp}.json'}")
    print(f"{len(results) - len(failed)} of {len(results)} checks passed" + (f"; failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
