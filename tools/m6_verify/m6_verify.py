#!/usr/bin/env python3
"""M6 exit-criterion check: ask a question on Day 4, get citations that seek to the right moment (ADR-0047, ADR-0046).

Standalone: it never imports from backend/src/insightex. It starts its own API server and worker on an isolated data
directory (the real library is untouched) that share the REAL GPU lease and the real Ollama, ingests the Day 4 lecture
through the real pipeline, and drives /ask and /warm-up over HTTP. It also loads, unloads and holds the GPU lease to
exercise the fallbacks. Nothing else may use the GPU, and no Ollama model may be loaded at the start.

    bash ~/insightex/scripts/run_in_env.sh python tools/m6_verify/m6_verify.py

See README.md in this folder. Evidence goes to docs/evidence/m6/ (counts, ids and timings; never question text).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVAL = Path.home() / "insightex-data" / "eval" / "day04_batch_vs_online"
GOLD = REPO / "tools" / "eval_retrieval" / "gold_spans.json"
G5 = REPO / "docs" / "evidence" / "m6"
FIVE = ["A01", "A14", "A16", "A26", "A19r"]
TOTAL_CHECKS = 13
RESULTS: list[dict] = []
LOG: list[str] = []
EVIDENCE: dict = {}


def say(line: str) -> None:
    LOG.append(line)
    print(line, flush=True)


def record(number: int, name: str, status: bool | str, evidence: str) -> bool:
    if isinstance(status, bool):
        status = "PASS" if status else "FAIL"
    RESULTS.append({"check": number, "name": name, "status": status, "evidence": evidence})
    say(f"{status:<4}  {number}. {name}: {evidence}")
    return status in ("PASS", "WARN")


class Abort(Exception):
    pass


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def is_hit(c: dict, spans: list[list[float]]) -> bool:
    """ADR-0043's hit rule: the window covers at least half of one gold span."""
    return any(overlap(c["start"], c["end"], s0, s1) >= 0.5 * (s1 - s0) for s0, s1 in spans)


def ollama_loaded(base: str) -> list[dict] | None:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/ps", timeout=5) as r:
            return json.loads(r.read()).get("models", [])
    except (OSError, ValueError):
        return None


def ollama_unload(base: str, model: str, timeout: float = 60) -> bool:
    req = urllib.request.Request(base.rstrip("/") + "/api/generate", data=json.dumps({"model": model, "keep_alive": 0}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not ollama_loaded(base):
            return True
        time.sleep(0.5)
    return False


def vram_used() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, check=True).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def flock_free(path: Path) -> bool:
    if not path.exists():
        return True
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


class System:
    """The isolated API + worker this run owns."""

    def __init__(self, args: argparse.Namespace, real: dict) -> None:
        self.args, self.real = args, real
        self.data = Path(args.data_dir).expanduser()
        self.base = f"http://127.0.0.1:{args.port}"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("INSIGHTEX__")}
        self.env.update({"INSIGHTEX_DATA": str(self.data), "INSIGHTEX__GPU__LEASE_PATH": real["lease_path"],
                         "INSIGHTEX__API__PORT": str(args.port)})
        self.env.pop("INSIGHTEX_CONFIG", None)
        self.api_proc: subprocess.Popen | None = None
        self.worker: subprocess.Popen | None = None
        self.logs = self.data / "m6_verify_logs"

    def start_api(self, extra_env: dict[str, str] | None = None) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        out = (self.logs / "api.out").open("ab")
        self.api_proc = subprocess.Popen([sys.executable, "-m", "insightex.api"], env={**self.env, **(extra_env or {})},
                                         stdout=out, stderr=out)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.api_proc.poll() is not None:
                raise Abort(f"the API server exited (code {self.api_proc.returncode}); see {self.logs / 'api.out'}")
            if self.get("/api/languages")[0] == 200:
                time.sleep(0.5)
                return
            time.sleep(0.5)
        raise Abort("the API server did not answer within 120 s")

    def stop_api(self) -> None:
        if self.api_proc is not None and self.api_proc.poll() is None:
            self.api_proc.send_signal(signal.SIGTERM)
            try:
                self.api_proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.api_proc.kill()
                self.api_proc.wait()

    def start_worker(self) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        out = (self.logs / "worker.out").open("ab")
        self.worker = subprocess.Popen([sys.executable, "-m", "insightex.cli", "worker"], env=self.env, stdout=out, stderr=out)
        time.sleep(3)
        if self.worker.poll() is not None:
            raise Abort(f"the worker exited at start (code {self.worker.returncode}); see {self.logs / 'worker.out'}")

    def stop_worker(self) -> None:
        if self.worker is not None and self.worker.poll() is None:
            self.worker.send_signal(signal.SIGTERM)
            try:
                self.worker.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.worker.kill()
                self.worker.wait()

    def stop_all(self) -> None:
        self.stop_worker()
        self.stop_api()

    def request(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw or b"null")
            except ValueError:
                return e.code, None
        except (urllib.error.URLError, ConnectionError):
            return 0, None

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: dict | None = None):
        return self.request("POST", path, body if body is not None else {})

    def cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "insightex.cli", *argv], env=self.env, capture_output=True, text=True,
                              timeout=1800, check=False)

    def api_log_lines(self) -> list[str]:
        path = self.data / "logs" / "api" / "api.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def ask_lines(self) -> list[dict]:
        out = []
        for line in self.api_log_lines():
            if " insightex.ask: " in line:
                out.append(json.loads(line.split(" insightex.ask: ", 1)[1]))
        return out


def wait_job(sysm: System, job_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        status, job = sysm.get(f"/api/jobs/{job_id}")
        if status == 200:
            line = " ".join(f"{s['name']}={s['status']}:{int(100 * s['progress'])}%" for s in job["stages"])
            if line != last:
                say(f"      {line}")
                last = line
            if job["status"] in ("succeeded", "failed", "cancelled"):
                return job
        time.sleep(0.5)
    raise Abort(f"job {job_id} did not finish within {timeout:g} s")


def ask(sysm: System, lecture: str, question: str):
    t0 = time.perf_counter()
    status, body = sysm.post(f"/api/lectures/{lecture}/ask", {"question": question})
    return status, body, (time.perf_counter() - t0) * 1000


def wait_model(base: str, loaded: bool, timeout: float) -> list[dict] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        models = ollama_loaded(base)
        if bool(models) == loaded:
            return models
        time.sleep(1)
    return None


def run(args: argparse.Namespace, sysm: System) -> None:
    real = sysm.real
    ollama_base, model = real["ollama_base_url"], real["ollama_model"]
    gold = {q["id"]: q for q in json.loads(GOLD.read_text(encoding="utf-8"))}
    questions = {q["id"]: q["question"] for q in json.loads((REPO / "tools" / "eval_retrieval" / "gold_questions.json").read_text(encoding="utf-8"))}
    g5_rows = {r["id"]: r for r in json.loads((G5 / "g5_rewrites.json").read_text(encoding="utf-8"))["rewrites"]}
    baseline = vram_used()

    # 1 -- ingest Day 4 through the real pipeline; the lecture is searchable with first_segment_start in its windows
    rc = sysm.cli("ingest-file", args.day4, "--confirm-rights", "--language", "hindi")
    try:
        queued = json.loads(rc.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        raise Abort(f"ingest-file failed: {(rc.stdout + rc.stderr)[-400:]}") from None
    lecture = queued["lecture_id"]
    t0 = time.monotonic()
    job = wait_job(sysm, queued["job_id"], args.job_timeout)
    names = [s["name"] for s in job["stages"]]
    status, doc = sysm.get(f"/api/lectures/{lecture}")
    windows_path = next((sysm.data / "workspaces" / lecture / "stages" / "index").glob("*/windows.json"), None)
    transcript_path = next((sysm.data / "workspaces" / lecture / "stages" / "asr").glob("*/transcript.json"), None)
    seg_start = {}
    if transcript_path:
        seg_start = {s["id"]: s["start"] for s in json.loads(transcript_path.read_text(encoding="utf-8"))["segments"]}
    wins = json.loads(windows_path.read_text(encoding="utf-8"))["windows"] if windows_path else []
    seek_ok = bool(wins) and all(w.get("first_segment_start") == seg_start.get(w["first_segment"]) and w["first_segment_start"] >= w["start"] for w in wins)
    duration_ok = status == 200 and abs((doc or {}).get("duration_s", 0) - 688.03) <= 1
    EVIDENCE["ingest_s"] = round(time.monotonic() - t0, 1)
    record(1, "Day 4 ingested (fetch, normalise, asr, index); lecture searchable; windows carry the first segment's start",
           job["status"] == "succeeded" and names == ["fetch", "normalise", "asr", "index"] and status == 200
           and doc["searchable"] is True and doc["max_question_chars"] == 300 and seek_ok and duration_ok,
           f"job {job['status']}, stages {names}, searchable {doc and doc.get('searchable')}, {len(wins)} windows, "
           f"first_segment_start matches the transcript for all: {seek_ok}, duration {doc and doc.get('duration_s')}, {EVIDENCE['ingest_s']} s")

    # 2 -- the ask box's refusals and limits
    refusals = {}
    for label, text in (("empty", ""), ("spaces", "   \n "), ("301 chars", "q" * 301)):
        s, b, _ = ask(sysm, lecture, text)
        refusals[label] = (s, (b or {}).get("error", {}).get("code"), text and text in json.dumps(b))
    s300, _, _ = ask(sysm, lecture, "q" * 300)
    s404 = ask(sysm, "yt-doesnotexist1", "q")[0]
    s409 = sysm.post(f"/api/lectures/{lecture}/ask", {"question": 5})[0]
    ok2 = (refusals["empty"][:2] == (400, "QUESTION_EMPTY") and refusals["spaces"][:2] == (400, "QUESTION_EMPTY")
           and refusals["301 chars"][:2] == (400, "QUESTION_TOO_LONG") and not refusals["301 chars"][2] and s300 == 200 and s404 == 404 and s409 == 422)
    record(2, "empty, blank and over-length questions are refused with clear codes (never echoed); 300 characters is accepted; unknown lecture 404",
           ok2, f"{refusals}; 300 chars -> {s300}; unknown lecture -> {s404}; non-text question -> {s409}")

    # 3 -- fallback: Ollama has nothing loaded
    if ollama_loaded(ollama_base):
        ollama_unload(ollama_base, model)
    s, b, ms = ask(sysm, lecture, questions["A19r"])
    ok3 = s == 200 and 1 <= len(b["citations"]) <= 3 and b["rewrite"] == {"used": False, "fallback_reason": "llm_not_loaded"} and ms < 2000
    record(3, "Roman Urdu question with no model loaded: results appear, no error, original-only search", ok3,
           f"HTTP {s}, {len(b['citations']) if s == 200 else '-'} citations, rewrite {b and b.get('rewrite')}, {ms:.0f} ms")

    # 4 -- warm-up loads the model with the context the rewrite uses
    s, b = sysm.post(f"/api/lectures/{lecture}/warm-up")
    t0 = time.monotonic()
    models = wait_model(ollama_base, True, 180)
    entry = next((m for m in (models or []) if m.get("name") == model), None)
    warm_s = time.monotonic() - t0
    record(4, "warm-up (202) loads the model in the background with the rewrite's context", s == 202 and entry is not None
           and entry.get("context_length") in (None, 8192),
           f"HTTP {s} {b}, loaded after {warm_s:.1f} s, context_length {entry and entry.get('context_length')}")
    EVIDENCE["warm_up_s"] = round(warm_s, 1)

    # 5 -- the five manual-checklist questions, model warm: rewrite used, a gold citation, a seek time inside its window
    detail = {}
    ok5 = True
    for qid in FIVE:
        s, b, ms = ask(sysm, lecture, questions[qid])
        if s != 200:
            ok5 = False
            detail[qid] = f"HTTP {s}"
            continue
        hits = [c["rank"] for c in b["citations"] if is_hit(c, gold[qid]["spans"])]
        seek_in = all(c["start"] <= c["seek_s"] < c["end"] for c in b["citations"])
        good = b["rewrite"]["used"] and len(b["citations"]) <= 3 and bool(hits) and seek_in
        ok5 &= good
        detail[qid] = {"gold_hit_ranks": hits, "rewrite_used": b["rewrite"]["used"], "ms": round(ms),
                       "seek_s": [c["seek_s"] for c in b["citations"]]}
    EVIDENCE["five_questions"] = detail
    record(5, f"{', '.join(FIVE)} with the model warm: rewrite used, one of the 3 citations covers the gold span, seek times inside their windows",
           ok5, json.dumps({k: (v if isinstance(v, str) else {"hit_ranks": v["gold_hit_ranks"], "ms": v["ms"]}) for k, v in detail.items()}))

    # 6 -- all 47 questions through /ask with the model warm: the same hits as the gated G5 run
    g5_b = {r["id"]: r["hits"] for r in json.loads((G5 / "g5_B_fused.json").read_text(encoding="utf-8"))["results"]}

    def g5_hit(qid: str) -> bool:
        kept: list[dict] = []
        for h in g5_b[qid]:  # de-duplicate (any overlap), then the top 3
            if all(overlap(h["start"], h["end"], k["start"], k["end"]) <= 0 for k in kept):
                kept.append(h)
        return any(is_hit(c, gold[qid]["spans"]) for c in kept[:3])

    mine, errors, fallbacks = {}, [], []
    for qid, text in questions.items():
        s, b, _ = ask(sysm, lecture, text)
        if s != 200:
            errors.append(qid)
            continue
        mine[qid] = any(is_hit(c, gold[qid]["spans"]) for c in b["citations"])
        if not b["rewrite"]["used"]:
            fallbacks.append(qid)
    differing = [q for q in mine if mine[q] != g5_hit(q)]
    sets = {"all": list(mine), "english": [q for q in mine if gold[q]["set"] in ("en", "hard")], "roman": [q for q in mine if gold[q]["set"] == "roman"]}
    recall = {k: round(sum(mine[q] for q in v) / len(v), 4) for k, v in sets.items()}
    EVIDENCE["recall_at_3_through_ask"] = recall
    record(6, "all 47 questions through /ask (model warm): no errors, no fallbacks, same hit/miss as the gated G5 run",
           not errors and not fallbacks and not differing,
           f"Recall@3 {recall}; errors {errors}; fallbacks {fallbacks}; differing from G5 {differing}")

    # 7 -- rewrite latency from the count log
    asks = [a for a in sysm.ask_lines() if a.get("event") == "ask" and a.get("rewrite_used")]
    rw = [a["rewrite_ms"] for a in asks]
    p95 = sorted(rw)[max(0, -(-95 * len(rw) // 100) - 1)] if rw else None
    EVIDENCE["rewrite_ms"] = {"n": len(rw), "median": round(statistics.median(rw), 1) if rw else None, "p95": p95, "max": max(rw) if rw else None}
    record(7, "rewrite call under the 2 s timeout for every warm question", bool(rw) and max(rw) <= 2000,
           f"{len(rw)} rewrites, median {EVIDENCE['rewrite_ms']['median']} ms, p95 {p95} ms, max {EVIDENCE['rewrite_ms']['max']} ms")

    # 8 -- GPU lease held by a job: gpu_busy, results still appear, warm-up skipped
    lease = Path(real["lease_path"])
    fd = os.open(lease, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        s, b, ms = ask(sysm, lecture, questions["A19r"])
        sw, _ = sysm.post(f"/api/lectures/{lecture}/warm-up")
        time.sleep(1.5)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    warm_lines = [a for a in sysm.ask_lines() if a.get("event") == "warm_up"]
    record(8, "a job holds the exclusive GPU lease: results still appear (gpu_busy), the warm-up is skipped",
           s == 200 and b["rewrite"] == {"used": False, "fallback_reason": "gpu_busy"} and bool(b["citations"])
           and sw == 202 and warm_lines and warm_lines[-1]["result"] == "skipped" and warm_lines[-1]["reason"] == "gpu_busy",
           f"ask HTTP {s} {b and b.get('rewrite')}; warm-up HTTP {sw}, logged {warm_lines[-1] if warm_lines else None}")

    # 9 -- timeout: restart the API with a 1 ms timeout (the model is still loaded)
    sysm.stop_api()
    sysm.start_api({"INSIGHTEX__RETRIEVAL__REWRITE_TIMEOUT_S": "0.001"})
    s, b, ms = ask(sysm, lecture, questions["A19r"])
    record(9, "rewrite slower than the timeout: results appear with the original search (timeout)",
           s == 200 and b["rewrite"] == {"used": False, "fallback_reason": "timeout"} and bool(b["citations"]),
           f"HTTP {s}, {b and b.get('rewrite')}, {ms:.0f} ms (timeout set to 0.001 s)")
    sysm.stop_api()
    sysm.start_api()

    # 10 -- the manual checklist's last step: Ollama unloaded again, A19r still gets results
    unloaded = ollama_unload(ollama_base, model)
    s, b, ms = ask(sysm, lecture, questions["A19r"])
    hits = [c["rank"] for c in (b or {}).get("citations", []) if is_hit(c, gold["A19r"]["spans"])]
    record(10, "Ollama unloaded again: A19r still returns citations without an error", unloaded and s == 200 and bool(b["citations"])
           and b["rewrite"]["fallback_reason"] == "llm_not_loaded",
           f"unloaded {unloaded}; HTTP {s}, {len(b['citations']) if s == 200 else '-'} citations, gold hit ranks {hits} (the original-only search may miss it), {ms:.0f} ms")

    # 11 -- privacy: nothing of any question or rewrite is in the API logs
    texts = [t for t in questions.values()] + [r["rewrite"] for r in g5_rows.values() if r.get("rewrite")] + ["q" * 50]
    haystack = "\n".join(sysm.api_log_lines()) + "\n" + (sysm.logs / "api.out").read_text(encoding="utf-8", errors="replace")
    leaked = [t[:20] for t in set(texts) if t in haystack]
    ask_lines = sysm.ask_lines()
    fields_ok = all(set(a) == {"event", "total_ms", "rewrite_ms", "search_ms", "rewrite_used", "fallback_reason", "citations"}
                    for a in ask_lines if a.get("event") == "ask")
    record(11, "API logs hold only count lines: no question or rewrite text, fixed field set", not leaked and fields_ok and len(ask_lines) > 50,
           f"{len(ask_lines)} count lines, fields as specified: {fields_ok}, texts found in logs: {len(leaked)}")

    # 12 -- the page and its scripts are served and the frontend tests pass
    s_page, page = sysm.get("/")
    s_js, _ = sysm.get("/ask.js")
    page_text = page.decode("utf-8", "replace") if isinstance(page, bytes) else ""
    tests = subprocess.run(["bash", str(REPO / "scripts" / "test_frontend.sh")], capture_output=True, text=True, check=False)
    record(12, "the page has the ask box and the index progress label; ask.js is served; frontend tests pass",
           s_page == 200 and s_js == 200 and 'id="ask-form"' in page_text and "Prepare for search" in page_text and tests.returncode == 0,
           f"/ {s_page}, /ask.js {s_js}, deno: {(tests.stdout or tests.stderr).strip().splitlines()[-1][-60:] if (tests.stdout or tests.stderr).strip() else ''}")

    # 13 -- the GPU is clean at the end
    time.sleep(3)
    after = vram_used()
    record(13, "no model is left loaded and GPU memory is back within 100 MiB of the start",
           not ollama_loaded(ollama_base) and baseline is not None and after is not None and after - baseline <= 100,
           f"before {baseline} MiB, after {after} MiB")


def write_evidence(out_dir: Path, started: datetime, args: argparse.Namespace, notes: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    results = sorted(RESULTS, key=lambda r: r["check"])
    failed = [r["check"] for r in results if r["status"] == "FAIL"]
    git = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    doc = {"started": started.isoformat(timespec="seconds"), "git_commit": git, "day4_file": Path(args.day4).name,
           "checks": results, "passed": sum(1 for r in results if r["status"] == "PASS"), "failed_checks": failed,
           "all_passed": not failed and {r["check"] for r in results if r["check"]} == set(range(1, TOTAL_CHECKS + 1)),
           "notes": notes, **EVIDENCE}
    path = out_dir / f"m6_verify_{stamp}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--day4", default=str(EVAL / "raw" / "lecture_test.mp4"))
    ap.add_argument("--data-dir", default=str(Path.home() / "insightex-data" / "m6_verify_run"))
    ap.add_argument("--port", type=int, default=8012)
    ap.add_argument("--job-timeout", type=float, default=1800)
    ap.add_argument("--out-dir", type=Path, default=REPO / "docs" / "evidence" / "m6")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    started = datetime.now(UTC)
    data = Path(args.data_dir).expanduser()
    if str(data.resolve()).startswith("/mnt/"):
        print("--data-dir must not be under /mnt (DrvFS)", file=sys.stderr)
        return 2
    out = subprocess.run([sys.executable, "-m", "insightex.cli", "gpu", "status", "--json"], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        print(f"ABORT  insightex gpu status failed: {out.stderr.strip()[-300:]}", file=sys.stderr)
        return 2
    real = json.loads(out.stdout)
    run_dir = Path(real["run_dir"])
    if not flock_free(run_dir / "worker.lock") or not flock_free(Path(real["lease_path"])):
        print("ABORT  a worker is running or the GPU lease is held; stop it first, then rerun", file=sys.stderr)
        return 2
    loaded = ollama_loaded(real["ollama_base_url"])
    if loaded is None:
        print("ABORT  Ollama is not reachable (start E:\\FYP\\start_ollama.ps1): the checks need it for the warm questions", file=sys.stderr)
        return 2
    if loaded:
        print(f"ABORT  Ollama has a model loaded ({', '.join(m.get('name', '?') for m in loaded)}); unload it first "
              f"(ollama stop <model>), then rerun: the ingest needs the GPU and the first checks need an empty Ollama", file=sys.stderr)
        return 2
    if data.exists() and any(data.iterdir()):
        if data.name == "m6_verify_run" and not args.keep:
            shutil.rmtree(data)
        else:
            print(f"ABORT  {data} exists and is not empty; remove it or pass another --data-dir", file=sys.stderr)
            return 2
    sysm = System(args, real)
    say(f"m6_verify: isolated data {data}, API {sysm.base}, shared GPU lease {real['lease_path']}, Ollama {real['ollama_base_url']}")
    aborted = None
    try:
        sysm.start_api()
        sysm.start_worker()
        run(args, sysm)
    except Abort as exc:
        aborted = str(exc)
    except Exception as exc:  # noqa: BLE001 - report and still clean up
        aborted = f"{type(exc).__name__}: {exc}"
    finally:
        sysm.stop_all()
        try:
            if ollama_loaded(real["ollama_base_url"]):
                ollama_unload(real["ollama_base_url"], real["ollama_model"])
        except OSError:
            pass
    notes: list[str] = []
    if aborted:
        say(f"ABORT  {aborted}")
        RESULTS.append({"check": 0, "name": "run completed", "status": "FAIL", "evidence": aborted})
    if args.keep:
        notes.append(f"kept {data}")
    else:
        shutil.rmtree(data, ignore_errors=True)
        notes.append(f"removed {data}")
    path = write_evidence(args.out_dir, started, args, notes)
    results = [r for r in RESULTS if r["check"]]
    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    passed = sum(1 for r in results if r["status"] == "PASS")
    say(f"\n{passed}/{TOTAL_CHECKS} checks passed" + (f"; failed: {', '.join(str(r['check']) for r in failed)}" if failed else "") + f"\nevidence: {path}")
    path.with_suffix(".log").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    return 1 if failed or len(results) < TOTAL_CHECKS else 0


if __name__ == "__main__":
    sys.exit(main())
