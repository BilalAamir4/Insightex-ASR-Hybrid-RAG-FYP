"""M0 exit script: one entry point that verifies the whole Insightex environment.

Run (cold boot, Ollama already started):
    bash scripts/run_in_env.sh python tools/verify_env.py        # or: bash scripts/verify_env.sh

Prints a PASS/FAIL/SKIP table and writes $INSIGHTEX_DATA/env_reports/<timestamp>.json.
Exit code 0 only if every check passes. Every GPU check runs in its own subprocess and the
parent confirms VRAM is released before the next one starts (VRAM contract).

Standalone: does not import from backend/. The Ollama call contract is exercised by running
`python -m insightex.llm.ollama_client --selftest` as a black-box subprocess.
"""
from __future__ import annotations

import datetime as dt
import importlib.metadata as md
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("INSIGHTEX_DATA", Path.home() / "insightex-data"))
OLLAMA_MODEL = "qwen3.5:latest"
VRAM_TOLERANCE_MIB = 200
CLIP_SRC = DATA / "eval/day04_batch_vs_online/eval/lecture_first10min.wav"
LOCKFILE = REPO / "requirements.lock.txt"
IGNORED_PACKAGES = {"insightex", "pip", "setuptools", "wheel"}  # editable repo install; pip freeze omits pip/setuptools/wheel


NVIDIA_SMI = shutil.which("nvidia-smi") or "/usr/lib/wsl/lib/nvidia-smi"


def smi_used_mib() -> int:
    out = subprocess.check_output(
        [NVIDIA_SMI, "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, timeout=30
    )
    return int(out.strip().splitlines()[0])


def wait_vram_at_most(limit_mib: int, timeout: float = 15.0) -> int:
    deadline, cur = time.monotonic() + timeout, smi_used_mib()
    while cur > limit_mib and time.monotonic() < deadline:
        time.sleep(1.0)
        cur = smi_used_mib()
    return cur


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ---------------------------------------------------------------- in-process checks (no CUDA)

def check_env_vars() -> str:
    problems = []
    for v in ("INSIGHTEX_HOME", "INSIGHTEX_DATA", "HF_HOME", "HF_HUB_OFFLINE", "OLLAMA_BASE_URL", "LD_LIBRARY_PATH"):
        if not os.environ.get(v):
            problems.append(f"{v} unset")
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        problems.append(f"HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')!r} (want 1)")
    if os.environ.get("OLLAMA_HOST", "").startswith("0.0.0.0"):
        problems.append("OLLAMA_HOST is 0.0.0.0 (must stay loopback)")
    entries = os.environ.get("LD_LIBRARY_PATH", "").split(":")
    if "" in entries:
        problems.append("LD_LIBRARY_PATH has an empty entry (trailing/leading/double colon)")
    dups = sorted({e for e in entries if e and entries.count(e) > 1})
    if dups:
        problems.append(f"LD_LIBRARY_PATH duplicates: {dups}")
    # cache locations must live on ext4, never on /mnt (DrvFS) and never be symlinked there
    for label, path in {
        "HF_HOME": os.environ.get("HF_HOME"), "TORCH_HOME": os.environ.get("TORCH_HOME"),
        "PIP_CACHE_DIR": os.environ.get("PIP_CACHE_DIR"), "~/.cache/pip": "~/.cache/pip",
        "~/.paddlex": "~/.paddlex", "~/.cache/paddle": "~/.cache/paddle",
    }.items():
        if not path:
            continue
        p = Path(path).expanduser()
        if str(p.resolve()).startswith("/mnt/"):
            problems.append(f"{label} resolves into /mnt: {p.resolve()}")
    if problems:
        raise AssertionError("; ".join(problems))
    return f"{len(entries)} LD_LIBRARY_PATH entries, HF_HOME={os.environ['HF_HOME']}, OLLAMA_BASE_URL={os.environ['OLLAMA_BASE_URL']}"


def check_lockfile() -> str:
    text = LOCKFILE.read_text()
    if not text.endswith("\n"):
        raise AssertionError("lockfile has no trailing newline (truncated?)")
    locked: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
        if not m:
            raise AssertionError(f"unparseable lockfile line: {line!r}")
        locked[norm(m.group(1))] = m.group(2)
    installed = {norm(d.metadata["Name"]): d.version for d in md.distributions()}
    missing = sorted(k for k in locked if k not in installed)
    wrong = sorted(f"{k}: lock {locked[k]} != installed {installed[k]}" for k in locked if k in installed and installed[k] != locked[k])
    extra = sorted(k for k in installed if k not in locked and k not in IGNORED_PACKAGES)
    if missing or wrong or extra:
        raise AssertionError(f"missing={missing} mismatched={wrong} not_in_lockfile={extra}")
    return f"{len(locked)} locked packages match the venv (ignored: {sorted(IGNORED_PACKAGES)})"


def check_ffmpeg() -> str:
    out = []
    for tool in ("ffmpeg", "ffprobe"):
        first = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        out.append(first.split(" Copyright")[0])
    return "; ".join(out)


def check_faiss() -> str:
    import faiss
    import numpy as np

    rng = np.random.default_rng(0)
    x = rng.standard_normal((50, 16)).astype("float32")
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    idx = faiss.IndexFlatIP(16)
    idx.add(x)
    scores, ids = idx.search(x[7:8], 3)
    if ids[0][0] != 7 or abs(scores[0][0] - 1.0) > 1e-4:
        raise AssertionError(f"self-search returned ids={ids[0].tolist()} scores={scores[0].tolist()}")
    return f"faiss {faiss.__version__}: IndexFlatIP 50x16, self-match id=7 score={scores[0][0]:.4f}"


def check_networkx() -> str:
    import networkx as nx

    g = nx.DiGraph()
    g.add_edge("batch learning", "online learning", relation="contrasts_with")
    g.add_edge("online learning", "learning rate", relation="uses")
    path = nx.shortest_path(g, "batch learning", "learning rate")
    if path != ["batch learning", "online learning", "learning rate"]:
        raise AssertionError(f"unexpected path {path}")
    return f"networkx {nx.__version__}: 3 nodes/2 edges, path ok"


def ollama_get(path: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(os.environ["OLLAMA_BASE_URL"].rstrip("/") + path, timeout=10) as r:
        return json.load(r)


def check_ollama_tags() -> str:
    names = [m["name"] for m in ollama_get("/api/tags").get("models", [])]
    if OLLAMA_MODEL not in names:
        raise AssertionError(f"{OLLAMA_MODEL!r} not in {names}")
    return f"/api/tags lists {OLLAMA_MODEL} (all: {names})"


# ---------------------------------------------------------------- GPU checks: run in a child process

def child_torch_cuda() -> dict:
    import torch

    if not torch.cuda.is_available():
        raise AssertionError("torch.cuda.is_available() is False")
    free, total = torch.cuda.mem_get_info()
    return {"torch": torch.__version__, "cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0),
            "free_mib": free // 2**20, "total_mib": total // 2**20}


def child_whisper() -> dict:
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory() as td:
        clip = Path(td) / "clip10.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "60", "-t", "10", "-i", str(CLIP_SRC),
                        "-ac", "1", "-ar", "16000", str(clip)], check=True, timeout=60)
        t0 = time.monotonic()
        model = WhisperModel("medium", device="cuda", compute_type="float16")
        load_s = time.monotonic() - t0
        t0 = time.monotonic()
        segs, info = model.transcribe(str(clip), language="ur", task="transcribe", beam_size=5, temperature=0.0)
        segs = list(segs)  # inference happens here; fails with libcublas error if LD_LIBRARY_PATH is wrong
        infer_s = time.monotonic() - t0
    n_chars = sum(len(s.text.strip()) for s in segs)
    if not segs or n_chars == 0:
        raise AssertionError("no transcribed text")
    return {"segments": len(segs), "chars": n_chars, "duration_s": round(info.duration, 1),
            "load_s": round(load_s, 2), "infer_s": round(infer_s, 2)}


def child_bge() -> dict:
    from sentence_transformers import SentenceTransformer

    t0 = time.monotonic()
    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    load_s = time.monotonic() - t0
    vec = model.encode(["batch learning versus online learning"], normalize_embeddings=True)
    if vec.shape != (1, 1024):
        raise AssertionError(f"shape {vec.shape}, want (1, 1024)")
    return {"dim": int(vec.shape[1]), "load_s": round(load_s, 2), "offline": os.environ.get("HF_HUB_OFFLINE") == "1"}


CHILDREN = {"torch_cuda": child_torch_cuda, "whisper": child_whisper, "bge_m3": child_bge}


def run_gpu_check(name: str, cmd: list[str], baseline: int) -> tuple[bool, str, dict]:
    """Run a check as a subprocess, then require VRAM back near baseline before returning."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    after = wait_vram_at_most(baseline + VRAM_TOLERANCE_MIB)
    released = after <= baseline + VRAM_TOLERANCE_MIB
    payload: dict = {}
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    ok = proc.returncode == 0 and payload.get("ok", False)
    detail = json.dumps(payload.get("result", {})) if ok else (payload.get("error") or (proc.stderr.strip().splitlines() or ["no output"])[-1])
    detail += f" | VRAM after exit {after} MiB (baseline {baseline})"
    if ok and not released:
        ok, detail = False, "VRAM not released: " + detail
    return ok, detail, payload.get("result", {})


def child_main(name: str) -> None:
    try:
        print(json.dumps({"ok": True, "result": CHILDREN[name]()}))
    except Exception as e:  # report to the parent, then exit non-zero
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        sys.exit(1)


def ollama_selftest_cmd(flag: str) -> list[str]:
    code = (
        "import json,runpy,sys;"
        f"sys.argv=['x','{flag}'];"
        "import io,contextlib;b=io.StringIO()\n"
        "try:\n"
        "  with contextlib.redirect_stdout(b): runpy.run_module('insightex.llm.ollama_client',run_name='__main__')\n"
        "  print(json.dumps({'ok':True,'result':json.loads(b.getvalue().strip().splitlines()[-1])}))\n"
        "except BaseException as e:\n"
        "  print(json.dumps({'ok':False,'error':f'{type(e).__name__}: {e}'}));sys.exit(1)\n"
    )
    return [sys.executable, "-c", code]


# ---------------------------------------------------------------- orchestration

def main() -> int:
    started = dt.datetime.now()
    results: list[dict] = []

    def record(name: str, ok: bool | None, detail: str, extra: dict | None = None) -> None:
        results.append({"check": name, "status": "PASS" if ok else ("SKIP" if ok is None else "FAIL"), "detail": detail, **(extra or {})})

    def run_inproc(name: str, fn) -> None:
        try:
            record(name, True, fn())
        except Exception as e:
            record(name, False, f"{type(e).__name__}: {e}")

    run_inproc("env vars / caches", check_env_vars)
    run_inproc("packages match lockfile", check_lockfile)
    run_inproc("ffmpeg / ffprobe", check_ffmpeg)
    run_inproc("faiss tiny index", check_faiss)
    run_inproc("networkx graph", check_networkx)

    baseline = None
    ollama_up = False
    try:
        record("ollama /api/tags lists model", True, check_ollama_tags())
        ollama_up = True
    except Exception as e:
        record("ollama /api/tags lists model", False, f"{type(e).__name__}: {e}")

    # GPU idle precondition: never start a CUDA stage next to a resident Ollama model
    resident = []
    if ollama_up:
        resident = [m["name"] for m in ollama_get("/api/ps").get("models", [])]
    try:
        baseline = smi_used_mib()
        gpu_idle_ok = not resident
        record("gpu idle baseline", gpu_idle_ok,
               f"{baseline} MiB used of 8192 with no model resident" if gpu_idle_ok
               else f"{baseline} MiB used; Ollama has {resident} loaded (run `ollama stop` first; not stopped automatically)",
               {"baseline_mib": baseline})
        if not gpu_idle_ok:
            baseline = None
    except Exception as e:
        record("gpu idle baseline", False, f"nvidia-smi failed: {e}")

    gpu_checks = [
        ("torch CUDA available", [sys.executable, __file__, "--child", "torch_cuda"]),
        ("faster-whisper medium fp16 (10 s clip)", [sys.executable, __file__, "--child", "whisper"]),
        ("bge-m3 offline, 1024-d", [sys.executable, __file__, "--child", "bge_m3"]),
    ]
    for name, cmd in gpu_checks:
        if baseline is None:
            record(name, None, "skipped: GPU not idle or nvidia-smi unavailable")
            continue
        ok, detail, res = run_gpu_check(name, cmd, baseline)
        record(name, ok, detail, {"result": res})

    if baseline is None or not ollama_up:
        record("chat_json schema-valid, 100% GPU", None, "skipped: Ollama down or GPU not idle")
        record("after unload VRAM within 200 MiB of baseline", None, "skipped")
    else:
        # Not run_gpu_check: the model must stay resident after this call so we can unload and measure.
        proc = subprocess.run(ollama_selftest_cmd("--selftest"), capture_output=True, text=True, timeout=900)
        payload = {}
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:
            pass
        res = payload.get("result", {})
        ok = bool(payload.get("ok")) and res.get("gpu_pct") == 100.0
        if payload.get("ok"):
            detail = json.dumps(res) + ("" if ok else " | NOT 100% GPU")
        else:
            detail = payload.get("error") or proc.stderr.strip()[-300:] or "no output"
        record("chat_json schema-valid, 100% GPU", ok, detail, {"result": res})
        proc = subprocess.run(ollama_selftest_cmd("--unload"), capture_output=True, text=True, timeout=120)
        after = wait_vram_at_most(baseline + VRAM_TOLERANCE_MIB)
        unloaded = False
        try:
            unloaded = bool(json.loads(proc.stdout.strip().splitlines()[-1]).get("result", {}).get("unloaded"))
        except Exception:
            pass
        ok = unloaded and after <= baseline + VRAM_TOLERANCE_MIB
        record("after unload VRAM within 200 MiB of baseline", ok,
               f"unloaded={unloaded}, VRAM {after} MiB vs baseline {baseline} MiB (delta {after - baseline:+d})")

    # ---- report
    w = max(len(r["check"]) for r in results)
    print(f"\nInsightex environment check, {started:%Y-%m-%d %H:%M:%S}\n")
    print(f"{'CHECK'.ljust(w)}  STATUS  DETAIL")
    for r in results:
        print(f"{r['check'].ljust(w)}  {r['status']:<6}  {r['detail'][:220]}")
    n_fail = sum(r["status"] == "FAIL" for r in results)
    n_skip = sum(r["status"] == "SKIP" for r in results)
    print(f"\n{sum(r['status'] == 'PASS' for r in results)} passed, {n_fail} failed, {n_skip} skipped")

    out_dir = DATA / "env_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{started:%Y%m%dT%H%M%S}.json"
    git = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    out.write_text(json.dumps({"started": started.isoformat(timespec="seconds"), "git_commit": git, "host_baseline_mib": baseline,
                               "all_passed": n_fail == 0 and n_skip == 0, "results": results}, indent=2))
    print(f"report: {out}")
    return 0 if n_fail == 0 and n_skip == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child_main(sys.argv[2])
    else:
        sys.exit(main())
