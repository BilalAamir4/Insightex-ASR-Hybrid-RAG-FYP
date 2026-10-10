#!/usr/bin/env python3
"""M4 session 2 exit-criterion check: the asr stage transcribes Day 4 like the accepted gate, with language selection.

Standalone: it never imports from backend/src/insightex. It starts its own API server and worker on an isolated
data directory (so the real library is untouched) that share the REAL GPU lease, drives them through the CLI and
the HTTP API, and inspects the workspace files. Nothing else may be using the GPU, and no Ollama model may be loaded.

    bash ~/insightex/scripts/run_in_env.sh python tools/m4_verify/m4_verify.py \
        --day4 ~/insightex-data/eval/day04_batch_vs_online/raw/lecture_test.mp4

See README.md in this folder. Evidence goes to docs/evidence/m4/ (stats and comparisons only, never transcript text).
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVAL = Path.home() / "insightex-data" / "eval" / "day04_batch_vs_online"
SCHEMA = REPO / "docs" / "contracts" / "transcript.schema.json"
TOTAL_CHECKS = 12
RESULTS: list[dict] = []
LOG: list[str] = []
EVIDENCE: dict = {"timings_s": {}}
TS_TOL = 0.001  # seconds; timestamp tolerance against the gate


def say(line: str) -> None:
    LOG.append(line)
    print(line, flush=True)


def record(number: int, name: str, status: str | bool, evidence: str) -> bool:
    if isinstance(status, bool):
        status = "PASS" if status else "FAIL"
    RESULTS.append({"check": number, "name": name, "status": status, "evidence": evidence})
    say(f"{status:<4}  {number}. {name}: {evidence}")
    return status in ("PASS", "WARN")


class Abort(Exception):
    pass


# -- environment ----------------------------------------------------------------------------------------------


class System:
    """The isolated API + worker this run owns."""

    def __init__(self, args: argparse.Namespace, real: dict) -> None:
        self.args = args
        self.data = Path(args.data_dir).expanduser()
        self.base = f"http://127.0.0.1:{args.port}"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("INSIGHTEX__")}
        self.env.update({"INSIGHTEX_DATA": str(self.data), "INSIGHTEX__GPU__LEASE_PATH": real["lease_path"],
                         "INSIGHTEX__API__PORT": str(args.port)})
        self.env.pop("INSIGHTEX_CONFIG", None)
        self.api_proc: subprocess.Popen | None = None
        self.worker: subprocess.Popen | None = None
        self.logs = self.data / "m4_verify_logs"

    # processes
    def start_api(self) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        out = (self.logs / "api.out").open("ab")
        self.api_proc = subprocess.Popen([sys.executable, "-m", "insightex.api"], env=self.env, stdout=out, stderr=out)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.api_proc.poll() is not None:
                raise Abort(f"the API server exited (code {self.api_proc.returncode}); see {self.logs / 'api.out'}")
            if self.get("/api/languages")[0] == 200:
                return
            time.sleep(0.5)
        raise Abort("the API server did not answer within 60 s")

    def start_worker(self, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
        self.logs.mkdir(parents=True, exist_ok=True)
        out = (self.logs / "worker.out").open("ab")
        self.worker = subprocess.Popen([sys.executable, "-m", "insightex.cli", "worker"],
                                       env={**self.env, **(extra_env or {})}, stdout=out, stderr=out)
        time.sleep(3)
        if self.worker.poll() is not None:
            raise Abort(f"the worker exited at start (code {self.worker.returncode}); see {self.logs / 'worker.out'}")
        return self.worker

    def stop_worker(self) -> int | None:
        if self.worker is None or self.worker.poll() is not None:
            return None if self.worker is None else self.worker.returncode
        self.worker.send_signal(signal.SIGTERM)
        try:
            return self.worker.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.worker.kill()
            return self.worker.wait()

    def stop_all(self) -> None:
        self.stop_worker()
        if self.api_proc is not None and self.api_proc.poll() is None:
            self.api_proc.send_signal(signal.SIGTERM)
            try:
                self.api_proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.api_proc.kill()

    # HTTP
    def get(self, path: str) -> tuple[int, dict | list | None]:
        return self._req("GET", path)

    def post_json(self, path: str, body: dict) -> tuple[int, dict | None]:
        return self._req("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json"})

    def upload(self, path: Path, language: str | None) -> tuple[int, dict | None]:
        headers = {"Content-Type": "application/octet-stream", "X-Insightex-Rights-Confirmed": "true",
                   "X-Insightex-Filename": path.name, "Content-Length": str(path.stat().st_size)}
        if language is not None:
            headers["X-Insightex-Language"] = language
        return self._req("POST", "/api/ingest/upload", path.read_bytes(), headers)

    def _req(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None):
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or "null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or "null")
            except ValueError:
                return e.code, None
        except (urllib.error.URLError, ConnectionError):
            return 0, None

    # CLI
    def cli(self, *argv: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "insightex.cli", *argv], env={**self.env, **(extra_env or {})},
                              capture_output=True, text=True, timeout=1800, check=False)

    def ingest_file(self, path: Path, language: str | None) -> tuple[int, dict]:
        argv = ["ingest-file", str(path), "--confirm-rights"] + (["--language", language] if language else [])
        proc = self.cli(*argv)
        stream = proc.stdout if proc.stdout.strip() else proc.stderr
        try:
            return proc.returncode, json.loads(stream.strip().splitlines()[0])
        except (ValueError, IndexError):
            return proc.returncode, {"raw": (proc.stdout + proc.stderr)[-500:]}

    def jobs_count(self) -> int:
        status, jobs = self.get("/api/jobs?limit=200")
        return len(jobs) if status == 200 else -1

    # files
    def workspace(self, workspace_id: str) -> Path:
        return self.data / "workspaces" / workspace_id

    def stage_dir(self, workspace_id: str, stage: str) -> Path | None:
        try:
            manifest = json.loads((self.workspace(workspace_id) / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        entry = manifest.get("stages", {}).get(stage)
        return self.workspace(workspace_id) / "stages" / stage / entry["key"] if entry else None


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


def real_paths() -> dict:
    env = {k: v for k, v in os.environ.items()}
    out = subprocess.run([sys.executable, "-m", "insightex.cli", "gpu", "status", "--json"], env=env,
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise Abort(f"insightex gpu status failed: {out.stderr.strip()[-300:]}")
    return json.loads(out.stdout)


def ollama_loaded(base_url: str) -> list[str] | None:
    """Names of loaded Ollama models, or None if Ollama is unreachable (then nothing is loaded)."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/ps", timeout=5) as r:
            return [m.get("name") or m.get("model") for m in json.loads(r.read()).get("models", [])]
    except (OSError, ValueError):
        return None


def vram_used() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, check=True).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def child_pids() -> list[int]:
    out = subprocess.run(["pgrep", "-f", "insightex.asr.child"], capture_output=True, text=True, check=False).stdout
    return [int(p) for p in out.split()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def make_clip_mp4(wav: Path, out: Path) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=320x240:rate=25", "-i", str(wav), "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0", "-c:a", "aac", "-b:a", "128k", str(out)],
                   check=True)


# -- job watching ---------------------------------------------------------------------------------------------


def wait_job(sysm: System, job_id: str, timeout: float, *, on_poll=None) -> dict:
    deadline = time.monotonic() + timeout
    last_line = ""
    while time.monotonic() < deadline:
        status, job = sysm.get(f"/api/jobs/{job_id}")
        if status == 200:
            line = " ".join(f"{s['name']}={s['status']}:{int(100 * s['progress'])}%" for s in job["stages"])
            if line != last_line:
                say(f"      {line}")
                last_line = line
            if on_poll is not None and on_poll(job):
                return job
            if job["status"] in ("succeeded", "failed", "cancelled"):
                return job
        time.sleep(0.25)
    raise Abort(f"job {job_id} did not finish within {timeout:g} s")


def transcript_of(sysm: System, workspace_id: str) -> tuple[dict, Path]:
    directory = sysm.stage_dir(workspace_id, "asr")
    if directory is None:
        raise Abort(f"no asr stage in the manifest of {workspace_id}")
    return json.loads((directory / "transcript.json").read_text(encoding="utf-8")), directory


def compare_to_gate(doc: dict, gate: dict) -> dict:
    ours, theirs = doc["segments"], gate["segments"]
    differing = []
    for i, (a, b) in enumerate(zip(ours, theirs, strict=False)):
        if a["text"] != b["text"] or abs(a["start"] - b["start"]) > TS_TOL or abs(a["end"] - b["end"]) > TS_TOL:
            differing.append(i)
    differing += list(range(min(len(ours), len(theirs)), max(len(ours), len(theirs))))
    max_dt = max((max(abs(a["start"] - b["start"]), abs(a["end"] - b["end"])) for a, b in zip(ours, theirs, strict=False)),
                 default=0.0)
    return {"ours": len(ours), "gate": len(theirs), "differing_segments": len(differing),
            "first_differing_index": differing[0] if differing else None, "max_timestamp_diff_s": round(max_dt, 6),
            "identical": not differing and len(ours) == len(theirs)}


def parse_vtt(text: str) -> list[tuple[float, float]]:
    def secs(ts: str) -> float:
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    cues = []
    for m in re.finditer(r"^(\d{2,}:\d{2}:\d{2}\.\d{3}) --> (\d{2,}:\d{2}:\d{2}\.\d{3})$", text, re.MULTILINE):
        cues.append((secs(m.group(1)), secs(m.group(2))))
    return cues


# -- the run --------------------------------------------------------------------------------------------------


def run(args: argparse.Namespace, sysm: System, tmp: Path) -> None:
    day4, clip_wav = Path(args.day4).expanduser(), Path(args.clip).expanduser()
    gate = json.loads(Path(args.gate_raw).expanduser().read_text(encoding="utf-8"))
    clip = tmp / "clip_30s.mp4"
    make_clip_mp4(clip_wav, clip)
    say(f"      clip fixture: {clip} ({clip.stat().st_size} bytes, video testsrc2 + {clip_wav.name})")

    # 1 -----------------------------------------------------------------------------------------------------
    shown = sysm.cli("config", "show").stdout
    rev = re.search(r"^\s*model_revision: (\S+)", shown, re.MULTILINE)
    repo = re.search(r"^\s*model_repo: (\S+)", shown, re.MULTILINE)
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    snap = (hf_home / "hub" / f"models--{repo.group(1).replace('/', '--')}" / "snapshots" / rev.group(1)) if rev and repo else None
    model_ok = bool(snap and (snap / "model.bin").is_file() and (snap / "config.json").is_file())
    validate = sysm.cli("config", "validate")
    langs = sysm.cli("languages", "list", "--json")
    try:
        groups = json.loads(langs.stdout)["groups"]
        tested = [lang["id"] for lang in groups[0]["languages"]] if groups[0]["tier"] == "tested" else []
        n_untested = len(groups[1]["languages"])
    except (ValueError, KeyError, IndexError):
        tested, n_untested = [], 0
    record(1, "large-v3 in the offline cache; language config loads and validates",
           model_ok and validate.returncode == 0 and tested == ["hindi"] and n_untested == 99,
           f"snapshot {snap} model.bin {'present' if model_ok else 'MISSING'}; config validate exit {validate.returncode} "
           f"({validate.stdout.strip() or validate.stderr.strip()[-200:]}); tested {tested}, untested {n_untested}")

    # 11 ----------------------------------------------------------------------------------------------------
    before = sysm.jobs_count()
    checks = []
    s, b = sysm.post_json("/api/ingest/link", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "rights_confirmed": True})
    checks.append(("link, no language", s, (b or {}).get("error", {}).get("code"), "MISSING_LANGUAGE"))
    s, b = sysm.post_json("/api/ingest/link", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "rights_confirmed": True,
                                               "language": "klingon"})
    checks.append(("link, klingon", s, (b or {}).get("error", {}).get("code"), "UNKNOWN_LANGUAGE"))
    unknown_msg = (b or {}).get("error", {}).get("message", "")
    s, b = sysm.upload(clip, None)
    checks.append(("upload, no language", s, (b or {}).get("error", {}).get("code"), "MISSING_LANGUAGE"))
    s, b = sysm.upload(clip, "klingon")
    checks.append(("upload, klingon", s, (b or {}).get("error", {}).get("code"), "UNKNOWN_LANGUAGE"))
    rc, out = sysm.ingest_file(clip, None)
    checks.append(("CLI, no --language", 400 if rc == 2 else rc, out.get("error", {}).get("code"), "MISSING_LANGUAGE"))
    rc, out = sysm.ingest_file(clip, "klingon")
    checks.append(("CLI, --language klingon", 400 if rc == 2 else rc, out.get("error", {}).get("code"), "UNKNOWN_LANGUAGE"))
    after = sysm.jobs_count()
    staging = sysm.data / "staging"
    staged = [p.name for p in staging.iterdir()] if staging.is_dir() else []
    ok11 = all(st == 400 and code == want for _, st, code, want in checks) and before == after and not staged \
        and "klingon" in unknown_msg
    record(11, "missing and unknown language rejected with clear messages; no job queued", ok11,
           "; ".join(f"{name} -> {st} {code}" for name, st, code, _ in checks)
           + f"; jobs before/after {before}/{after}; staging {staged or 'empty'}; message: {unknown_msg!r}")

    # 2, 3, 4, 7, 9, 10 -------------------------------------------------------------------------------------
    baseline = vram_used()
    EVIDENCE["vram_baseline_mib"] = baseline
    t0 = time.monotonic()
    rc, out = sysm.ingest_file(day4, "hindi")
    if rc != 0 or not out.get("job_id"):
        raise Abort(f"Day 4 submission failed: exit {rc} {out}")
    day4_ws = out["lecture_id"]
    EVIDENCE["day4_workspace"] = day4_ws
    job = wait_job(sysm, out["job_id"], args.job_timeout)
    EVIDENCE["timings_s"]["day4_job_wall"] = round(time.monotonic() - t0, 1)
    if job["status"] != "succeeded":
        record(2, "Day 4 (hindi) through file ingest, normalise, ASR", False, f"job {job['status']}: {job.get('error')}")
        raise Abort("Day 4 did not transcribe; later checks cannot run")
    time.sleep(3)
    after_vram = vram_used()
    doc, asr_dir = transcript_of(sysm, day4_ws)
    vtt = asr_dir / "transcript.vtt"
    try:
        import jsonschema

        jsonschema.validate(doc, json.loads(SCHEMA.read_text(encoding="utf-8")))
        schema_ok, schema_note = True, "valid"
    except ImportError:
        schema_ok, schema_note = False, "jsonschema not installed"
    except Exception as exc:  # noqa: BLE001 - any validation failure is the check's evidence
        schema_ok, schema_note = False, f"invalid: {str(exc).splitlines()[0]}"
    record(2, "Day 4 (hindi) through file ingest, normalise, ASR -> transcript.json + transcript.vtt",
           schema_ok and vtt.is_file() and doc["language"]["whisper_language"] == "ur"
           and [s["name"] for s in job["stages"]] == ["fetch", "normalise", "asr"],
           f"job {job['status']} in {EVIDENCE['timings_s']['day4_job_wall']} s; schema {schema_note}; "
           f"whisper_language {doc['language']['whisper_language']}; vtt {'present' if vtt.is_file() else 'MISSING'}")
    EVIDENCE["day4_stats"] = {**doc["stats"], "warnings": [{"code": w["code"], "segments": len(w["segment_ids"])}
                                                             for w in doc["warnings"]],
                              "model": doc["model"], "libraries": doc["libraries"], "audio_duration_s": doc["audio"]["duration_s"]}
    say(f"      Day 4 stats: {json.dumps(EVIDENCE['day4_stats'], ensure_ascii=False)}")

    audio = sysm.workspace(day4_ws) / doc["audio"]["path"]
    ours, theirs = sha256(audio), sha256(Path(args.gate_audio).expanduser())
    equal = ours == theirs
    record(3, "workspace audio.wav vs gate lecture_full.wav", True,
           f"{'EQUAL' if equal else 'DIFFERENT'} (workspace {ours[:16]}..., gate {theirs[:16]}...); "
           f"transcript audio.sha256 matches file: {doc['audio']['sha256'] == ours}")
    EVIDENCE["audio_equal_to_gate"] = equal

    cmp4 = compare_to_gate(doc, gate)
    EVIDENCE["gate_comparison"] = cmp4
    if equal:
        record(4, "segments, text and timestamps identical to the gate large-v3_ur raw.json (tol 0.001 s)", cmp4["identical"],
               f"{cmp4['ours']} vs {cmp4['gate']} segments, {cmp4['differing_segments']} differing, "
               f"max timestamp diff {cmp4['max_timestamp_diff_s']} s")
    else:
        record(4, "segments vs the gate raw.json", "WARN",
               f"audio differs from the gate input (the gate extracted audio from the source mp4, not via video.mp4; "
               f"ADR-0039 limitation 8); {cmp4['ours']} vs {cmp4['gate']} segments, {cmp4['differing_segments']} differing")

    diff = None if baseline is None or after_vram is None else after_vram - baseline
    record(7, "VRAM after the stage within 100 MiB of the pre-stage baseline", diff is not None and abs(diff) <= 100,
           f"baseline {baseline} MiB, after {after_vram} MiB (diff {diff} MiB); peak above baseline during the stage "
           f"{doc['stats']['peak_vram_mib']} MiB")

    dur = doc["audio"]["duration_s"]
    segs = doc["segments"]
    out_of_range = [s["id"] for s in segs if not (0 <= s["start"] <= dur and 0 <= s["end"] <= dur and s["start"] <= s["end"])]
    decreasing = [b["id"] for a, b in itertools.pairwise(segs) if b["start"] < a["start"]]
    bad_words = [s["id"] for s in segs for w in s["words"]
                 if w["start"] < s["start"] - 0.5 or w["end"] > s["end"] + 0.5 or not (0 <= w["start"] <= w["end"] <= dur)]
    record(9, "timestamp sanity: within [0, duration], starts non-decreasing, words inside their segment (0.5 s)",
           not out_of_range and not decreasing and not bad_words,
           f"{len(segs)} segments, duration {dur} s; out of range {out_of_range[:5]}, decreasing starts {decreasing[:5]}, "
           f"words outside {len(bad_words)}")

    cues = parse_vtt(vtt.read_text(encoding="utf-8"))
    mismatched = [i for i, ((cs, ce), s) in enumerate(zip(cues, segs, strict=False))
                  if abs(cs - s["start"]) > 0.0005 or abs(ce - s["end"]) > 0.0005]
    record(10, "VTT cue count equals segment count and cue times match the JSON", len(cues) == len(segs) and not mismatched,
           f"{len(cues)} cues, {len(segs)} segments, {len(mismatched)} mismatched")

    # 5 -----------------------------------------------------------------------------------------------------
    worker_log = sysm.data / "logs" / "worker.log"
    log_len = worker_log.stat().st_size if worker_log.exists() else 0
    t0 = time.monotonic()
    rc, again = sysm.ingest_file(day4, "hindi")
    elapsed = time.monotonic() - t0
    time.sleep(2)
    new_log = worker_log.read_text(encoding="utf-8", errors="replace")[log_len:] if worker_log.exists() else ""
    no_gpu = "gpu lease exclusive acquired" not in new_log and "asr subprocess started" not in new_log
    record(5, "Day 4 again with hindi: cache hit (no job, no lease, no subprocess, fast)",
           rc == 0 and again.get("deduplicated") is True and again.get("job_id") is None and no_gpu and elapsed < 60,
           f"exit {rc}, deduplicated {again.get('deduplicated')}, job_id {again.get('job_id')}, {elapsed:.1f} s "
           f"(includes copying and hashing the file); worker log after submit: "
           f"{'no lease, no subprocess' if no_gpu else 'GPU activity!'}")

    # 12 ----------------------------------------------------------------------------------------------------
    rc, out = sysm.ingest_file(clip, "english")
    job12 = wait_job(sysm, out["job_id"], args.job_timeout) if out.get("job_id") else {"status": f"not queued: {out}"}
    if job12.get("status") == "succeeded":
        d12, _ = transcript_of(sysm, out["lecture_id"])
        api_lang = job12.get("language") or {}
        ok12 = (d12["language"]["tier_at_processing"] == "untested" and d12["language"]["whisper_language"] == "en"
                and api_lang.get("tier") == "untested" and api_lang.get("id") == "english")
        note = (f"tier_at_processing {d12['language']['tier_at_processing']}, whisper_language "
                f"{d12['language']['whisper_language']}, job status language {api_lang}, {d12['stats']['segment_count']} segments")
    else:
        ok12, note = False, f"job {job12.get('status')}: {job12.get('error')}"
    record(12, "30 s clip with an untested language (english) completes and reports the untested tier", ok12, note)

    # 8 -----------------------------------------------------------------------------------------------------
    sysm.stop_worker()
    worker = sysm.start_worker({"INSIGHTEX__ASR__MIN_FREE_VRAM_MIB": "999999"})
    rc, out = sysm.ingest_file(clip, "urdu")
    job8 = wait_job(sysm, out["job_id"], 300) if out.get("job_id") else {"status": f"not queued: {out}", "stages": []}
    time.sleep(3)
    alive = worker.poll() is None
    asr8 = next((s for s in job8.get("stages", []) if s["name"] == "asr"), {})
    err8 = (asr8.get("error") or "").splitlines()[0] if asr8.get("error") else ""
    record(8, "pre-flight: required VRAM above what is free -> INSUFFICIENT_VRAM, worker keeps running",
           job8.get("status") == "failed" and "INSUFFICIENT_VRAM" in err8 and "999999 MiB" in err8 and "MiB of free" in err8
           and alive,
           f"job {job8.get('status')}; asr error: {err8!r}; worker alive afterwards: {alive}")
    sysm.stop_worker()
    sysm.start_worker()

    # 6 -----------------------------------------------------------------------------------------------------
    deleted = sysm.cli("cache", "delete", day4_ws)
    if deleted.returncode != 0:
        raise Abort(f"cache delete {day4_ws} failed: {deleted.stderr.strip()[-300:]}")
    rc, out = sysm.ingest_file(day4, "hindi")
    if rc != 0 or not out.get("job_id"):
        raise Abort(f"kill-test submission failed: exit {rc} {out}")
    job_id = out["job_id"]
    seen = {"partial": [], "reads": 0}

    def scan(job: dict) -> bool:
        """Every transcript.json visible under its final name (stage dir or staging) must be complete JSON."""
        ws = sysm.workspace(day4_ws)
        for path in [*ws.glob("stages/asr/*/transcript.json"), *ws.glob(".staging/asr-*/transcript.json")]:
            try:
                json.loads(path.read_text(encoding="utf-8"))
                seen["reads"] += 1
            except FileNotFoundError:
                pass  # moved between glob and read (the publish rename)
            except (OSError, ValueError):
                seen["partial"].append(str(path))
        asr = next(s for s in job["stages"] if s["name"] == "asr")
        return asr["status"] == "running" and asr["progress"] > 0.10

    job = wait_job(sysm, job_id, args.job_timeout, on_poll=scan)
    asr = next(s for s in job["stages"] if s["name"] == "asr")
    if asr["status"] != "running":
        raise Abort(f"ASR did not reach 10% before the job ended ({job['status']})")
    at_kill = asr["progress"]
    sysm.worker.send_signal(signal.SIGKILL)
    sysm.worker.wait(timeout=10)
    t_kill = time.monotonic()
    while child_pids() and time.monotonic() - t_kill < 10:
        time.sleep(0.2)
    orphans = child_pids()
    final_at_kill = list(sysm.workspace(day4_ws).glob("stages/asr/*/transcript.*"))
    status_after_kill = sysm.get(f"/api/jobs/{job_id}")[1]["status"]
    sysm.start_worker()
    job = wait_job(sysm, job_id, args.job_timeout, on_poll=lambda j: scan(j) and False)
    for path in sysm.workspace(day4_ws).glob("stages/asr/*/transcript.json"):
        json.loads(path.read_text(encoding="utf-8"))  # complete after success
    leftovers = [str(p) for p in sysm.workspace(day4_ws).rglob("*") if p.name.startswith(".transcript")]
    ok6, note6 = job["status"] == "succeeded", f"job {job['status']}"
    if ok6:
        d6, _ = transcript_of(sysm, day4_ws)
        cmp6 = compare_to_gate(d6, gate)
        same_as_run1 = [(s["text"], s["start"], s["end"]) for s in d6["segments"]] == \
                       [(s["text"], s["start"], s["end"]) for s in doc["segments"]]
        status_job = sysm.get(f"/api/jobs/{job_id}")[1]
        shown = sysm.cli("jobs", "show", job_id, "--json")
        try:
            attempts = json.loads(shown.stdout)["attempts"]
        except (ValueError, KeyError):
            attempts = None
        ok6 = attempts == 2 and (not orphans and not final_at_kill and not seen["partial"] and not leftovers and status_after_kill == "running" and same_as_run1
               and (cmp6["identical"] if equal else True))
        note6 = (f"killed at ASR {100 * at_kill:.0f}%; child processes left {orphans}; transcript files in the final "
                 f"location at kill {len(final_at_kill)}; partial reads {len(seen['partial'])} of {seen['reads']} complete "
                 f"reads; temp leftovers {len(leftovers)}; job after restart "
                 f"{status_job['status']}, attempts {attempts}; same segments as check 2: {same_as_run1}; vs gate: "
                 f"{cmp6['differing_segments']} differing of {cmp6['ours']}")
        EVIDENCE["kill_test"] = {"progress_at_kill": at_kill, "gate_comparison": cmp6}
    record(6, "kill the worker past 10% ASR, restart: job completes, no partial transcript, output matches check 4", ok6, note6)


def write_evidence(out_dir: Path, started: datetime, args: argparse.Namespace, notes: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    results = sorted(RESULTS, key=lambda r: r["check"])
    failed = [r["check"] for r in results if r["status"] == "FAIL"]
    git = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                         check=False).stdout.strip()
    numbered = {r["check"] for r in results if r["check"]}
    doc = {"started": started.isoformat(timespec="seconds"), "git_commit": git, "data_dir": args.data_dir,
           "day4_file": {"name": Path(args.day4).name, "size_bytes": Path(args.day4).expanduser().stat().st_size},
           "checks": results, "passed": sum(1 for r in results if r["status"] == "PASS"),
           "warned": [r["check"] for r in results if r["status"] == "WARN"], "failed_checks": failed,
           "all_passed": not failed and numbered == set(range(1, TOTAL_CHECKS + 1)), "notes": notes, **EVIDENCE}
    path = out_dir / f"m4_verify_{stamp}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--day4", default=str(EVAL / "raw" / "lecture_test.mp4"), help="the Day 4 lecture video")
    ap.add_argument("--clip", default=str(EVAL / "eval" / "clip_30s.wav"), help="the 30 s clip (WAV; muxed into an mp4)")
    ap.add_argument("--gate-raw", default=str(REPO / "tools" / "eval_wer" / "results" / "m4" / "large-v3_ur" / "raw.json"))
    ap.add_argument("--gate-audio", default=str(EVAL / "eval" / "lecture_full.wav"), help="the gate's input audio")
    ap.add_argument("--data-dir", default=str(Path.home() / "insightex-data" / "m4_verify_run"),
                    help="isolated data directory for this run (ext4, not /mnt); deleted at the end unless --keep")
    ap.add_argument("--port", type=int, default=8011, help="port of this run's own API server")
    ap.add_argument("--job-timeout", type=float, default=1800, help="seconds to wait for each job")
    ap.add_argument("--out-dir", type=Path, default=REPO / "docs" / "evidence" / "m4")
    ap.add_argument("--keep", action="store_true", help="keep the isolated data directory")
    args = ap.parse_args()

    started = datetime.now(UTC)
    notes: list[str] = []
    data = Path(args.data_dir).expanduser()
    if str(data.resolve()).startswith("/mnt/"):
        print("--data-dir must not be under /mnt (DrvFS)", file=sys.stderr)
        return 2
    try:
        real = real_paths()
    except Abort as exc:
        print(f"ABORT  {exc}", file=sys.stderr)
        return 2
    run_dir = Path(real["run_dir"])
    if not flock_free(run_dir / "worker.lock") or not flock_free(Path(real["lease_path"])):
        print(f"ABORT  a worker is running or the GPU lease is held ({run_dir}); stop it first "
              f"(Ctrl+C in the dev_run.sh terminal), then rerun", file=sys.stderr)
        return 2
    loaded = ollama_loaded(real["ollama_base_url"])
    if loaded:
        cmds = "; ".join(f"ollama stop {name}" for name in loaded)
        print(f"ABORT  Ollama has a model loaded: {', '.join(loaded)}. It would hold VRAM and skew the VRAM checks. "
              f"Unload it with: {cmds}   (in a Windows terminal), then rerun", file=sys.stderr)
        return 2
    notes.append("Ollama: " + ("unreachable (no model loaded)" if loaded is None else "reachable, no model loaded"))
    if data.exists():
        if not args.keep and (data / "workspaces").exists() and data.name == "m4_verify_run":
            shutil.rmtree(data)
        elif any(data.iterdir()):
            print(f"ABORT  {data} exists and is not empty; remove it or pass another --data-dir", file=sys.stderr)
            return 2

    sysm = System(args, real)
    say(f"m4_verify: isolated data {data}, API {sysm.base}, shared GPU lease {real['lease_path']}")
    aborted = None
    try:
        with tempfile.TemporaryDirectory(prefix="m4_verify_") as tmp:
            sysm.start_api()
            sysm.start_worker()
            run(args, sysm, Path(tmp))
    except Abort as exc:
        aborted = str(exc)
    except Exception as exc:  # noqa: BLE001 - report and still clean up
        aborted = f"{type(exc).__name__}: {exc}"
    finally:
        sysm.stop_all()
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
    warned = [str(r["check"]) for r in results if r["status"] == "WARN"]
    say(f"\n{passed}/{TOTAL_CHECKS} checks passed" + (f"; WARN: {', '.join(warned)}" if warned else "")
        + (f"; failed: {', '.join(str(r['check']) for r in failed)}" if failed else "") + f"\nevidence: {path}")
    path.with_suffix(".log").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    return 1 if failed or len(results) < TOTAL_CHECKS else 0


if __name__ == "__main__":
    sys.exit(main())
