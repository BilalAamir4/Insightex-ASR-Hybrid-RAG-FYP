#!/usr/bin/env python3
"""M2 exit-criterion check: the Day 4 lecture normalises through the HTTP upload path; odd files are rejected cleanly.

Standalone: it never imports from backend/src/insightex. It talks to the running server over HTTP, calls the CLI
by subprocess, inspects outputs with ffprobe/ffmpeg and builds its own small fixtures in a temp directory.
Start the server and a worker first (bash ~/insightex/scripts/dev_run.sh), then:

    bash ~/insightex/scripts/run_in_env.sh python tools/m2_verify/m2_verify.py --day4 <path to the Day 4 mp4>

See README.md in this folder. Evidence goes to docs/evidence/m2/ (never the Day 4 media or its transcript).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from array import array
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS: list[dict] = []
LOG: list[str] = []
CREATED_LECTURES: set[str] = set()  # deleted again at the end unless --keep
EVIDENCE: dict = {"timings_s": {}}


def say(line: str) -> None:
    LOG.append(line)
    print(line, flush=True)


def record(number: int, name: str, ok: bool | None, evidence: str) -> bool:
    RESULTS.append({"check": number, "name": name, "status": "SKIP" if ok is None else "PASS" if ok else "FAIL",
                    "evidence": evidence})
    say(f"{'SKIP' if ok is None else 'PASS' if ok else 'FAIL'}  {number}. {name}: {evidence}")
    return bool(ok)


class Abort(Exception):
    pass


# -- HTTP helpers (stdlib only) ---------------------------------------------------------------------------

class Api:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        parts = urllib.parse.urlsplit(self.base)
        self.host, self.port = parts.hostname or "127.0.0.1", parts.port or 80

    def get(self, path: str) -> tuple[int, dict | None]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as r:
                return r.status, json.loads(r.read() or "null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or "null")
            except ValueError:
                return e.code, None

    def delete(self, path: str) -> int:
        req = urllib.request.Request(self.base + path, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def upload(self, path: Path | None, *, data: bytes | None = None, name: str | None = None, rights: str | None = "true",
               on_progress=None, chunk: int = 1 << 20) -> tuple[int, dict | None, float]:
        """POST the file as a raw streamed body. Returns (status, json body, seconds spent sending)."""
        size = len(data) if data is not None else path.stat().st_size
        conn = http.client.HTTPConnection(self.host, self.port, timeout=600)
        headers = {"Content-Type": "application/octet-stream", "Content-Length": str(size),
                   "X-Insightex-Filename": urllib.parse.quote(name or (path.name if path else "upload.bin"))}
        if rights is not None:
            headers["X-Insightex-Rights-Confirmed"] = rights
        t0 = time.monotonic()
        conn.putrequest("POST", "/api/ingest/upload")
        for k, v in headers.items():
            conn.putheader(k, v)
        conn.endheaders()
        sent, next_report = 0, 0.1
        source = iter([data]) if data is not None else _read_chunks(path, chunk)
        for block in source:
            conn.send(block)
            sent += len(block)
            if on_progress and sent / size >= next_report:
                on_progress(sent, size, time.monotonic() - t0)
                next_report += 0.1
        resp = conn.getresponse()
        seconds = time.monotonic() - t0
        raw = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(raw or "null"), seconds
        except ValueError:
            return resp.status, None, seconds

    def wait_job(self, job_id: str, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, job = self.get(f"/api/jobs/{job_id}")
            if status == 200 and job["status"] in ("succeeded", "failed", "cancelled"):
                return job
            time.sleep(0.5)
        raise Abort(f"job {job_id} did not finish within {timeout:g} s (is a worker running?)")


def _read_chunks(path: Path, size: int):
    with open(path, "rb") as f:
        while block := f.read(size):
            yield block


def raw_request(host: str, port: int, head: bytes, body: bytes = b"", *, wait_response: bool = True,
                close_after_send: bool = False) -> tuple[int | None, float]:
    """Send raw bytes; return (status code or None, seconds until the status line arrived)."""
    t0 = time.monotonic()
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(head + body)
        if close_after_send:
            return None, time.monotonic() - t0
        if not wait_response:
            return None, 0.0
        s.settimeout(10)
        line = s.recv(200).split(b"\r\n", 1)[0].decode("latin1")
        parts = line.split()
        return (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None), time.monotonic() - t0


# -- ffmpeg / ffprobe helpers ---------------------------------------------------------------------------------

def ff(*args: str | Path) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise Abort(f"ffmpeg {' '.join(map(str, args))}: {proc.stderr.strip()[-300:]}")


def ffprobe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def encoder_available(name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False).stdout
    return any(len(p := line.split()) >= 2 and p[1] == name for line in out.splitlines())


def mp4_moov_before_mdat(path: Path) -> bool:
    """Walk the top-level boxes; True if `moov` comes before `mdat`."""
    with open(path, "rb") as f:
        size = path.stat().st_size
        pos = 0
        order = []
        while pos + 8 <= size:
            f.seek(pos)
            header = f.read(16)
            length, kind = struct.unpack(">I4s", header[:8])
            if length == 1:
                length = struct.unpack(">Q", header[8:16])[0]
            elif length == 0:
                length = size - pos
            order.append(kind.decode("latin1"))
            if length < 8:
                break
            pos += length
    return "moov" in order and "mdat" in order and order.index("moov") < order.index("mdat")


def flash_time(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi", "-i", f"movie=filename='{video}',signalstats",
         "-show_entries", "frame=pts_time:frame_tags=lavfi.signalstats.YAVG", "-of", "json"],
        capture_output=True, text=True, check=True).stdout
    for frame in json.loads(out)["frames"]:
        if float(frame["tags"]["lavfi.signalstats.YAVG"]) > 128:
            return float(frame["pts_time"])
    raise Abort("no flash found in video.mp4")


def beep_time(wav_path: Path) -> float:
    with wave.open(str(wav_path)) as w:
        rate = w.getframerate()
        samples = array("h")
        samples.frombytes(w.readframes(w.getnframes()))
    limit = 0.25 * 32767
    for i, s in enumerate(samples):
        if abs(s) > limit:
            return i / rate
    raise Abort("no beep found in audio.wav")


def beep_time_in_mp4(video: Path, ignore_editlist: bool) -> float:
    """Beep onset in video.mp4's audio track, decoded with timestamps honoured or with edit lists ignored."""
    pre = ["-ignore_editlist", "1"] if ignore_editlist else []
    raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *pre, "-i", str(video), "-map", "0:a:0",
                          "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    samples = array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    for i, v in enumerate(samples):
        if abs(v) > 0.25 * 32767:
            return i / 16000
    raise Abort("no beep found in video.mp4")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


# -- fixtures ------------------------------------------------------------------------------------------------

FLASH_AT, FLASH_LEN, FPS = 5.0, 0.2, 25
FLASH_SRC = (f"color=c=black:s=320x240:r={FPS}:d=15,"
             f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,{FLASH_AT},{FLASH_AT + FLASH_LEN})'")
V12 = ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=12"]
A12 = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=12"]
X264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]


def make_fixtures(d: Path) -> dict[str, Path]:
    fx: dict[str, Path] = {}
    fx["audio_only"] = d / "audio_only.m4a"
    ff(*A12, "-c:a", "aac", fx["audio_only"])
    fx["video_only"] = d / "video_only.mp4"
    ff(*V12, *X264, fx["video_only"])
    fx["text"] = d / "text.mp4"
    fx["text"].write_bytes(b"This is not a video. It is plain text pretending to be an mp4 file.\n" * 200)
    fx["short"] = d / "short_5s.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=5", "-f", "lavfi", "-i",
       "sine=frequency=440:sample_rate=44100:duration=5", *X264, "-c:a", "aac", fx["short"])
    fx["small_ok"] = d / "small_ok.mp4"
    ff(*V12, *A12, *X264, "-c:a", "aac", "-shortest", fx["small_ok"])
    # Flash at 5.0 s and beep at 5.0 s on the container clock, but the audio stream starts 1.5 s late.
    flash = d / "flash.mp4"
    ff("-f", "lavfi", "-i", FLASH_SRC, *X264, flash)
    beep = d / "beep.m4a"
    onset = FLASH_AT - 1.5
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs='if(between(t\\,{onset}\\,{onset + FLASH_LEN})\\,0.5*sin(2*PI*1000*t)\\,0)':s=48000:d=15",
       "-c:a", "aac", beep)
    fx["sync"] = d / "sync_delayed.mp4"
    ff("-i", flash, "-itsoffset", "1.5", "-i", beep, "-map", "0:v", "-map", "1:a", "-c", "copy", fx["sync"])
    if encoder_available("libx265"):
        fx["hevc"] = d / "hevc.mp4"
        ff(*V12, *A12, "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error", "-c:a", "aac",
           "-shortest", fx["hevc"])
    return fx


# -- lecture files ---------------------------------------------------------------------------------------------

def stage_dir(data_dir: Path, lecture_id: str, stage: str, must_have: str) -> Path | None:
    base = data_dir / "workspaces" / lecture_id / "stages" / stage
    if not base.is_dir():
        return None
    candidates = [p for p in base.iterdir() if (p / must_have).is_file()]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def staging_files(data_dir: Path) -> list[str]:
    d = data_dir / "staging"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def jobs_count(api: Api) -> int:
    return len((api.get("/api/jobs?limit=200")[1]) or [])


def error_text(job: dict) -> str:
    return " | ".join(filter(None, [job.get("error"), *(s.get("error") for s in job.get("stages", []))]))


# -- checks ---------------------------------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    api = Api(args.base_url)
    data_dir = Path(args.data_dir).expanduser()
    day4 = Path(args.day4).expanduser()
    if not day4.is_file():
        raise Abort(f"--day4 {day4} is not a file")

    # 1
    status, limits = api.get("/api/ingest/limits")
    if not record(1, "server reachable", status == 200 and bool(limits), f"GET /api/ingest/limits -> {status} {limits}"):
        raise Abort("server not reachable; start it with scripts/dev_run.sh")
    max_bytes = limits["max_upload_bytes"]

    # 2
    local_hash = sha256_of(day4)
    marks: list[str] = []

    def progress(sent: int, size: int, secs: float) -> None:
        marks.append(f"{100 * sent // size}%")
        say(f"      upload {100 * sent // size:3d}%  {sent / 2**20:8.1f} MiB  {sent / 2**20 / max(secs, 1e-6):6.1f} MiB/s")

    status, body, up_s = api.upload(day4, on_progress=progress)
    lecture_id = (body or {}).get("lecture_id")
    job = None
    if status == 202 and body.get("job_id"):
        CREATED_LECTURES.add(lecture_id)
        t0 = time.monotonic()
        job = api.wait_job(body["job_id"], args.job_timeout)
        EVIDENCE["timings_s"]["normalise_job_wall"] = round(time.monotonic() - t0, 2)
    EVIDENCE["timings_s"]["upload"] = round(up_s, 2)
    ok2 = status == 202 and job is not None and job["status"] == "succeeded" and len(marks) >= 5
    record(2, "Day 4 uploaded over HTTP with progress; job completes", ok2,
           f"HTTP {status}, upload {up_s:.1f} s, {len(marks)} progress marks, job {job['status'] if job else None}"
           + (f" ({error_text(job)[:200]})" if job and job['status'] != 'succeeded' else ""))
    if not ok2:
        raise Abort("Day 4 did not normalise; later Day 4 checks cannot run")

    norm = stage_dir(data_dir, lecture_id, "normalise", "video.mp4")
    fetch = stage_dir(data_dir, lecture_id, "fetch", "source.json")
    if norm is None or fetch is None:
        raise Abort(f"stage output directories for {lecture_id} not found under {data_dir}")
    video, wav, thumb = norm / "video.mp4", norm / "audio.wav", norm / "thumbnail.jpg"
    pv, pa = ffprobe(video), ffprobe(wav)
    EVIDENCE["ffprobe_video_mp4"], EVIDENCE["ffprobe_audio_wav"] = pv, pa

    # 3
    vs = next((s for s in pv["streams"] if s["codec_type"] == "video"), {})
    as_ = next((s for s in pv["streams"] if s["codec_type"] == "audio"), {})
    ws = next((s for s in pa["streams"] if s["codec_type"] == "audio"), {})
    moov = mp4_moov_before_mdat(video)
    ok3 = (vs.get("codec_name") == "h264" and vs.get("pix_fmt") in ("yuv420p", "yuvj420p") and as_.get("codec_name") == "aac"
           and moov and ws.get("codec_name") == "pcm_s16le" and int(ws.get("sample_rate", 0)) == 16000
           and int(ws.get("channels", 0)) == 1 and thumb.is_file() and thumb.stat().st_size > 0)
    record(3, "Day 4 artifacts: h264/aac with moov first, wav pcm_s16le 16 kHz mono, thumbnail", ok3,
           f"video {vs.get('codec_name')}/{vs.get('pix_fmt')}, audio {as_.get('codec_name')}, moov-before-mdat={moov}, "
           f"wav {ws.get('codec_name')} {ws.get('sample_rate')} Hz x{ws.get('channels')}, thumbnail={thumb.is_file()}")

    # 4
    d_wav, d_mp4, d_src = float(pa["format"]["duration"]), float(pv["format"]["duration"]), float(ffprobe(day4)["format"]["duration"])
    ok4 = abs(d_wav - d_mp4) <= 1.0 and abs(d_mp4 - d_src) <= max(2.0, 0.01 * d_src)
    record(4, "Day 4 durations: |wav-mp4| <= 1 s, |mp4-source| <= max(2 s, 1%)", ok4,
           f"wav {d_wav:.3f} s, mp4 {d_mp4:.3f} s, source {d_src:.3f} s; |wav-mp4|={abs(d_wav - d_mp4):.3f}, "
           f"|mp4-source|={abs(d_mp4 - d_src):.3f} (limit {max(2.0, 0.01 * d_src):.2f})")

    # 5
    src = json.loads((fetch / "source.json").read_text())
    info = json.loads((norm / "normalise.json").read_text())
    decision = info.get("decision")
    ok5 = (src.get("kind") == "upload" and src.get("via") == "http" and src.get("sha256") == local_hash
           and bool(decision) and bool(info.get("normaliser_version")) and isinstance(info.get("warnings"), list))
    EVIDENCE["day4"] = {"lecture_id": lecture_id, "decision": decision, "warnings": info.get("warnings"),
                        "normaliser_version": info.get("normaliser_version"), "normalise_timings_s": info.get("timings_s"),
                        "source_json": {k: src.get(k) for k in ("kind", "via", "sha256", "size_bytes", "received_at")}}
    EVIDENCE["timings_s"]["normalise_stage"] = (info.get("timings_s") or {}).get("total")
    record(5, "Day 4 source.json/normalise.json: kind, via, sha256, decision, version, warnings", ok5,
           f"kind={src.get('kind')} via={src.get('via')} sha256 {'matches' if src.get('sha256') == local_hash else 'DIFFERS'} "
           f"decision={decision and {k: decision.get(k) for k in ('video', 'audio')}} "
           f"normaliser_version={info.get('normaliser_version')} warnings={info.get('warnings')}")

    # 6
    jobs_before = jobs_count(api)
    status, body, _ = api.upload(day4)
    ok6 = status == 200 and body == {"lecture_id": lecture_id, "job_id": None, "deduplicated": True} and jobs_count(api) == jobs_before
    record(6, "re-upload of Day 4 is deduplicated with no new job", ok6, f"HTTP {status} {body}; jobs {jobs_before} -> {jobs_count(api)}")

    # 7
    with tempfile.TemporaryDirectory(prefix="m2_verify_") as tmp:
        fx = make_fixtures(Path(tmp))
        say(f"      fixtures built in {tmp}: {', '.join(sorted(fx))}")
        outcomes = []
        for key, code in (("audio_only", "NO_VIDEO_STREAM"), ("video_only", "NO_AUDIO_STREAM"),
                          ("text", "NOT_A_VIDEO"), ("short", "TOO_SHORT")):
            status, body, _ = api.upload(fx[key])
            if status != 202:
                outcomes.append((key, False, f"HTTP {status} {body}"))
                continue
            rejected_job = api.wait_job(body["job_id"], args.job_timeout)
            lid = body["lecture_id"]
            no_dir = not (data_dir / "workspaces" / lid).exists() and api.get(f"/api/lectures/{lid}")[0] == 404
            outcomes.append((key, rejected_job["status"] == "failed" and code in error_text(rejected_job) and no_dir,
                             f"{code}: job {rejected_job['status']}, code in error={code in error_text(rejected_job)}, no lecture dir={no_dir}"))
        time.sleep(1)
        leftover = staging_files(data_dir)
        outcomes.append(("staging", not leftover, f"staging files left: {leftover}"))
        record(7, "rejections over HTTP: right code, no lecture dir, staging empty", all(o[1] for o in outcomes),
               "; ".join(f"{k}: {t}" for k, _, t in outcomes))

        # 8
        if "hevc" in fx:
            status, body, _ = api.upload(fx["hevc"])
            hevc_job = api.wait_job(body["job_id"], args.job_timeout) if status == 202 else None
            if status == 202:
                CREATED_LECTURES.add(body["lecture_id"])
            d = stage_dir(data_dir, body["lecture_id"], "normalise", "normalise.json") if status == 202 else None
            dec = json.loads((d / "normalise.json").read_text()).get("decision") if d else None
            record(8, "HEVC fixture accepted with video=transcode", bool(hevc_job and hevc_job["status"] == "succeeded"
                   and dec and dec.get("video") == "transcode"), f"HTTP {status}, job {hevc_job and hevc_job['status']}, decision {dec and {k: dec.get(k) for k in ('video', 'audio')}}")
        else:
            record(8, "HEVC fixture accepted with video=transcode", None, "this ffmpeg has no libx265 encoder")

        # 9
        status, body, _ = api.upload(fx["sync"])
        if status == 202:
            CREATED_LECTURES.add(body["lecture_id"])
        sync_job = api.wait_job(body["job_id"], args.job_timeout) if status == 202 else None
        d = stage_dir(data_dir, body["lecture_id"], "normalise", "video.mp4") if status == 202 else None
        if sync_job and sync_job["status"] == "succeeded" and d:
            f, b = flash_time(d / "video.mp4"), beep_time(d / "audio.wav")
            limit = 1.0 / FPS  # one frame of the fixture's frame rate
            b_ignore = beep_time_in_mp4(d / "video.mp4", True)
            EVIDENCE["sync"] = {"flash_s": f, "beep_wav_s": b, "beep_mp4_edit_lists_ignored_s": b_ignore,
                                "offset_wav_ms": round((b - f) * 1000, 1),
                                "offset_edit_lists_ignored_ms": round((b_ignore - f) * 1000, 1), "limit_ms": limit * 1000}
            record(9, "flash/beep fixture with audio delayed 1.5 s: |flash-beep| <= one frame (audio.wav and video.mp4 with edit lists ignored)",
                   abs(f - b) <= limit and abs(f - b_ignore) <= limit,
                   f"flash {f:.3f} s, beep {b:.3f} s, offset {(b - f) * 1000:+.1f} ms; edit lists ignored: beep {b_ignore:.3f} s, "
                   f"offset {(b_ignore - f) * 1000:+.1f} ms (limit {limit * 1000:.0f} ms)")
        else:
            record(9, "flash/beep fixture with audio delayed 1.5 s: |flash-beep| <= one frame", False,
                   f"HTTP {status}, job {sync_job and sync_job['status']} {sync_job and error_text(sync_job)[:150]}")

        # 10: raw socket, half the body, close
        declared = 8 * 1024 * 1024
        head = (f"POST /api/ingest/upload HTTP/1.1\r\nHost: {api.host}:{api.port}\r\nContent-Type: application/octet-stream\r\n"
                f"Content-Length: {declared}\r\nX-Insightex-Filename: half.mp4\r\nX-Insightex-Rights-Confirmed: true\r\n\r\n").encode()
        raw_request(api.host, api.port, head, os.urandom(declared // 2), close_after_send=True)
        deadline = time.monotonic() + 5
        while staging_files(data_dir) and time.monotonic() < deadline:
            time.sleep(0.2)
        left = staging_files(data_dir)
        healthy = api.get("/api/ingest/limits")[0] == 200
        status, body, _ = api.upload(None, data=b"busy slot probe: plain text\n", name="probe.mp4")
        slot_free = status in (200, 202)
        if status == 202:
            api.wait_job(body["job_id"], args.job_timeout)
        record(10, "interrupted upload leaves no staging file in 5 s; server healthy; busy slot freed",
               not left and healthy and slot_free, f"staging after: {left}, healthy={healthy}, next upload HTTP {status}")

        # 11
        status, body, _ = api.upload(None, data=b"x" * 100, rights=None)
        record(11, "missing rights header -> 400 RIGHTS_NOT_CONFIRMED", status == 400 and (body or {}).get("error", {}).get("code") == "RIGHTS_NOT_CONFIRMED", f"HTTP {status} {body}")

        # 12
        head = (f"POST /api/ingest/upload HTTP/1.1\r\nHost: {api.host}:{api.port}\r\nContent-Type: application/octet-stream\r\n"
                f"Content-Length: {max_bytes + 1}\r\nX-Insightex-Filename: big.mp4\r\nX-Insightex-Rights-Confirmed: true\r\n\r\n").encode()
        code, secs = raw_request(api.host, api.port, head)
        record(12, "oversize Content-Length -> 413 in under 1 s without sending the body", code == 413 and secs < 1.0,
               f"HTTP {code} after {secs * 1000:.0f} ms (limit {max_bytes} bytes)")

        # 13
        before = jobs_count(api)
        proc = subprocess.run([sys.executable, "-m", "insightex.cli", "ingest-file", str(fx["small_ok"]), "--confirm-rights", "--wait"],
                              capture_output=True, text=True, timeout=args.job_timeout, check=False)
        out = {}
        try:
            out = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            pass
        if out.get("lecture_id"):
            CREATED_LECTURES.add(out["lecture_id"])
        record(13, "CLI ingest-file on a small fixture succeeds", proc.returncode == 0 and out.get("status") == "succeeded",
               f"exit {proc.returncode}, outcome {out.get('status')}, jobs {before} -> {jobs_count(api)}"
               + (f", stderr: {proc.stderr.strip()[-200:]}" if proc.returncode else ""))

    # Evidence that must come from the Day 4 lecture was collected above; remove what this run added.
    EVIDENCE["day4_artifact_dir"] = str(norm)


def cleanup(api: Api) -> list[str]:
    notes = []
    for lid in sorted(CREATED_LECTURES):
        notes.append(f"{lid}: DELETE -> {api.delete('/api/lectures/' + lid)}")
    return notes


def write_evidence(out_dir: Path, started: datetime, args: argparse.Namespace, cleanup_notes: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = [r["check"] for r in RESULTS if r["status"] == "FAIL"]
    git = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    doc = {"started": started.isoformat(timespec="seconds"), "git_commit": git, "base_url": args.base_url,
           "day4_file": {"name": Path(args.day4).name, "size_bytes": Path(args.day4).expanduser().stat().st_size},
           "checks": RESULTS, "passed": passed, "total": len(RESULTS), "failed_checks": failed,
           "all_passed": not failed and len(RESULTS) == 13, "cleanup": cleanup_notes,
           **{k: v for k, v in EVIDENCE.items() if k not in ("ffprobe_video_mp4", "ffprobe_audio_wav")}}
    (out_dir / f"m2_verify_{stamp}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (out_dir / f"m2_verify_{stamp}.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    for key, name in (("ffprobe_video_mp4", "day4_ffprobe_video_mp4"), ("ffprobe_audio_wav", "day4_ffprobe_audio_wav")):
        if key in EVIDENCE:
            (out_dir / f"{name}_{stamp}.json").write_text(json.dumps(EVIDENCE[key], indent=2) + "\n", encoding="utf-8")
    return out_dir / f"m2_verify_{stamp}.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--data-dir", default=os.environ.get("INSIGHTEX_DATA", str(Path.home() / "insightex-data")))
    ap.add_argument("--day4", required=True, help="path of the Day 4 lecture video")
    ap.add_argument("--job-timeout", type=float, default=900, help="seconds to wait for each job")
    ap.add_argument("--out-dir", type=Path, default=REPO / "docs" / "evidence" / "m2")
    ap.add_argument("--keep", action="store_true", help="keep the lectures this run created in the library")
    args = ap.parse_args()

    started = datetime.now(UTC)
    api = Api(args.base_url)
    aborted = None
    try:
        run(args)
    except Abort as exc:
        aborted = str(exc)
        say(f"ABORT  {aborted}")
    except (OSError, urllib.error.URLError) as exc:
        aborted = f"{type(exc).__name__}: {exc}"
        say(f"ABORT  {aborted}")
    notes = [] if args.keep else cleanup(api)
    if aborted:
        RESULTS.append({"check": 0, "name": "run completed", "status": "FAIL", "evidence": aborted})
    path = write_evidence(args.out_dir, started, args, notes)
    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    total = len([r for r in RESULTS if r["check"] != 0])
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    say(f"\n{passed}/{total} checks passed" + (f"; failed: {', '.join(str(r['check']) for r in failed)}" if failed else "")
        + f"\nevidence: {path}")
    (path.with_suffix(".log")).write_text("\n".join(LOG) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
