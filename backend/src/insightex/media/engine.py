"""The normalise engine (ADR-0036): one function that turns a staged source file into the playable artefacts.

    probe -> validate -> normalise -> extract audio -> verify -> thumbnail

`normalise_media` is called by the `normalise` stage for every source (link or file). It writes
`video.mp4`, `audio.wav` and `thumbnail.jpg` into `out_dir` and returns the record the stage saves as
`normalise.json`. Timeline rule: `audio.wav` is derived from the finished `video.mp4`, never from the
source, and is padded so its t=0 is the player's t=0. A rejected file raises `IngestRejected` with one
code from the closed set in `ingest/errors.py`. CPU only; no GPU lease.
"""

from __future__ import annotations

import functools
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from insightex.ingest.errors import ErrorCode, IngestRejected
from insightex.ingest.settings import IngestSettings
from insightex.media import ffmpeg, policy

log = logging.getLogger(__name__)

NORMALISER_VERSION = "2"  # bump when a change here alters video.mp4 / audio.wav / normalise.json; feeds the stage key
VIDEO_NAME, AUDIO_NAME, THUMB_NAME = "video.mp4", "audio.wav", "thumbnail.jpg"
STDERR_LINES = 20
_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?[0-9.]+|-inf)\s*dB")

Progress = Callable[[float, str], None]


# -- environment -----------------------------------------------------------------------------------

@functools.cache
def available_decoders() -> frozenset[str]:
    out = subprocess.run([ffmpeg.FFMPEG, "-hide_banner", "-decoders"], capture_output=True, text=True, timeout=30, check=False).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"[VAS.][F.][S.][X.][B.][D.]", parts[0]):
            names.add(parts[1])
    return frozenset(names)


@functools.cache
def ffmpeg_version() -> str:
    out = subprocess.run([ffmpeg.FFMPEG, "-version"], capture_output=True, text=True, timeout=30, check=False).stdout
    return out.splitlines()[0] if out else "unknown"


def tail(text: str, lines: int = STDERR_LINES) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


# -- pre-checks (rules 1 and 2) --------------------------------------------------------------------

def check_size(size_bytes: int, max_bytes: int) -> None:
    if size_bytes == 0:
        raise IngestRejected(ErrorCode.EMPTY_FILE)
    if size_bytes > max_bytes:
        raise IngestRejected(ErrorCode.TOO_LARGE, details=f"{size_bytes} > {max_bytes} bytes")


def check_disk(size_bytes: int, directory: Path, cfg: IngestSettings) -> None:
    """Free space on the filesystem holding `directory` must be at least factor x size + reserve."""
    need = int(cfg.disk_free_factor * size_bytes) + cfg.disk_free_reserve_bytes
    free = shutil.disk_usage(directory).free
    if free < need:
        raise IngestRejected(ErrorCode.INSUFFICIENT_DISK, details=f"free {free} bytes < required {need} bytes")


# -- probing ---------------------------------------------------------------------------------------

def probe_raw(path: Path, cfg: IngestSettings) -> dict[str, Any]:
    """`ffprobe -show_format -show_streams` as a dictionary. Failure, timeout or unreadable JSON is NOT_A_VIDEO."""
    cmd = [ffmpeg.FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.ffprobe_timeout_s, check=False)
    except subprocess.TimeoutExpired as exc:
        raise IngestRejected(ErrorCode.NOT_A_VIDEO, details=f"ffprobe timed out after {cfg.ffprobe_timeout_s} s") from exc
    if proc.returncode != 0:
        raise IngestRejected(ErrorCode.NOT_A_VIDEO, details=tail(proc.stderr))
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError as exc:
        raise IngestRejected(ErrorCode.NOT_A_VIDEO, details="ffprobe returned invalid JSON") from exc
    return data if isinstance(data, dict) else {}


def _run(args: list[str], cfg: IngestSettings, duration: float, on_fraction=None) -> None:
    timeout = max(cfg.ffmpeg_timeout_min_s, cfg.ffmpeg_timeout_factor * duration)
    try:
        ffmpeg.run_ffmpeg(args, duration, on_fraction, timeout_s=timeout)
    except ffmpeg.FFmpegError as exc:
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, details=tail(exc.stderr) or str(exc)) from exc


# -- ffmpeg arguments ------------------------------------------------------------------------------

def video_args(src: Path, dst: Path, streams: policy.Streams, decision: policy.Decision, cfg: IngestSettings) -> list[str]:
    """D2/D3: map exactly the two chosen streams; copy or transcode each; faststart; no subtitles, data or chapters."""
    args = [
        "-i", str(src),
        "-map", f"0:{streams.video['index']}", "-map", f"0:{streams.audio['index']}",
        "-sn", "-dn", "-map_chapters", "-1",
    ]
    if decision.video == "copy":
        args += ["-c:v", "copy"]
    else:
        filters = (["yadif"] if decision.deinterlace else []) + [
            f"scale=w=-2:h='min({cfg.transcode_max_height},trunc(ih/2)*2)'"
        ]
        args += [
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-force_key_frames", f"expr:gte(t,n_forced*{cfg.keyframe_interval_s:g})",
            "-fps_mode", "vfr",  # keep source frame timing; the mp4 muxer would otherwise default to constant frame rate
        ]
    if decision.audio == "copy":
        args += ["-c:a", "copy"]
    else:
        args += ["-c:a", "aac", "-b:a", f"{cfg.audio_bitrate_kbps}k", "-ar", "48000"]
        if decision.downmix:
            args += ["-ac", "2"]
        args += ["-af", "aresample=async=1:first_pts=0"]
    args += ["-movflags", "+faststart", "-f", "mp4", str(dst)]
    return args


def audio_args(video: Path, dst: Path) -> list[str]:
    """D4: ASR audio comes from the finished video.mp4; the padding filter puts its t=0 on the player's t=0."""
    return [
        "-i", str(video), "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0",
        "-ac", str(ffmpeg.ASR_CHANNELS), "-ar", str(ffmpeg.ASR_SAMPLE_RATE), "-c:a", ffmpeg.ASR_CODEC, "-f", "wav", str(dst),
    ]


# -- verification ----------------------------------------------------------------------------------

def moov_before_mdat(path: Path) -> bool:
    """True if the first top-level `moov` atom comes before the first `mdat` (the file plays before it has fully loaded)."""
    size = path.stat().st_size
    first: dict[bytes, int] = {}
    with path.open("rb") as f:
        pos = 0
        while pos + 8 <= size:
            f.seek(pos)
            header = f.read(16)
            length = int.from_bytes(header[:4], "big")
            kind = header[4:8]
            if length == 1 and len(header) >= 16:
                length = int.from_bytes(header[8:16], "big")
            elif length == 0:
                length = size - pos
            if length < 8:
                break
            first.setdefault(kind, pos)
            pos += length
    return b"moov" in first and b"mdat" in first and first[b"moov"] < first[b"mdat"]


def _fnum(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def verify_outputs(video: Path, audio: Path, source_duration: float, cfg: IngestSettings) -> dict[str, Any]:
    """Rule 8: structure, duration, start time and padding of the outputs. Returns the measurements; raises on failure."""
    probe = probe_raw(video, cfg)
    streams = probe.get("streams") or []
    vids = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    auds = [s for s in streams if s.get("codec_type") == "audio"]
    if (len(vids) != 1 or vids[0].get("codec_name") != "h264" or vids[0].get("pix_fmt") not in policy.VIDEO_COPY_PIX_FMTS
            or len(auds) != 1 or auds[0].get("codec_name") != "aac"):
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, details="video.mp4 is not exactly one h264 yuv420p and one aac stream")
    if not moov_before_mdat(video):
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, details="video.mp4 has its moov atom after mdat")

    out_duration = _fnum((probe.get("format") or {}).get("duration")) or 0.0
    tolerance = max(cfg.duration_tolerance_s, cfg.duration_tolerance_frac * source_duration)
    if abs(out_duration - source_duration) > tolerance:
        raise IngestRejected(ErrorCode.TRUNCATED, details=f"video.mp4 {out_duration:.2f} s vs source {source_duration:.2f} s")

    starts = [policy.start_time_of(s) for s in (vids[0], auds[0])]
    if min(starts) < -cfg.sync_tolerance_s or min(starts) > cfg.sync_tolerance_s:
        raise IngestRejected(ErrorCode.SYNC_CHECK_FAILED, details=f"video.mp4 stream start times {starts}")

    try:
        with wave.open(str(audio), "rb") as w:
            wav_ok = (w.getsampwidth() == 2 and w.getframerate() == ffmpeg.ASR_SAMPLE_RATE
                      and w.getnchannels() == ffmpeg.ASR_CHANNELS and w.getcomptype() == "NONE")
    except (wave.Error, EOFError) as exc:
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, details=f"audio.wav unreadable: {exc}") from exc
    if not wav_ok:
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, details="audio.wav is not pcm_s16le 16 kHz mono")
    wav_dur = wav_duration(audio)

    a_start = policy.start_time_of(auds[0])
    a_dur = _fnum(auds[0].get("duration"))
    if a_dur is None:
        a_dur = max(out_duration - a_start, 0.0)
    padding = wav_dur - a_dur
    if abs(padding - a_start) > cfg.sync_tolerance_s:
        raise IngestRejected(
            ErrorCode.SYNC_CHECK_FAILED,
            details=f"audio.wav {wav_dur:.3f} s - video.mp4 audio {a_dur:.3f} s = {padding:.3f} s, audio starts at {a_start:.3f} s",
        )
    return {
        "video_mp4_duration_s": round(out_duration, 3),
        "audio_wav_duration_s": round(wav_dur, 3),
        "video_mp4_audio_duration_s": round(a_dur, 3),
        "video_mp4_start_times_s": [round(t, 3) for t in starts],
        "audio_start_s": round(a_start, 3),
        "padding_s": round(padding, 3),
        "moov_before_mdat": True,
    }


def mean_volume_db(audio: Path) -> float | None:
    """volumedetect mean_volume of a WAV in dBFS; None if it could not be measured."""
    proc = subprocess.run(
        [ffmpeg.FFMPEG, "-hide_banner", "-nostdin", "-i", str(audio), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300, check=False,
    )
    m = _MEAN_VOLUME_RE.search(proc.stderr)
    if not m:
        return None
    return -math.inf if m.group(1) == "-inf" else float(m.group(1))


# -- the engine ------------------------------------------------------------------------------------

def _thumbnail(video: Path, source_image: Path | None, dst: Path, duration_s: float, cfg: IngestSettings) -> None:
    """Source thumbnail if the fetch stage saved one, else a frame at 10% of the duration."""
    if source_image is not None and source_image.is_file():
        try:
            ffmpeg.image_to_jpeg(source_image, dst, cfg)
            return
        except (ffmpeg.FFmpegError, OSError) as exc:
            log.info("source thumbnail unusable (%s); using a video frame", exc)
    try:
        ffmpeg.extract_frame_jpeg(video, dst, duration_s * 0.10, cfg)
    except ffmpeg.FFmpegError as exc:
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, "A thumbnail couldn't be created.", tail(exc.stderr)) from exc
    if not dst.is_file():
        raise IngestRejected(ErrorCode.TRANSCODE_FAILED, "A thumbnail couldn't be created.")


def normalise_media(
    source: Path,
    out_dir: Path,
    cfg: IngestSettings,
    *,
    max_bytes: int,
    thumbnail_src: Path | None = None,
    progress: Progress = lambda fraction, message: None,
) -> dict[str, Any]:
    """Validate `source` and write video.mp4, audio.wav and thumbnail.jpg into `out_dir`.

    Returns the engine's record (probe summary, decision, warnings, timings, verify measurements,
    normaliser and ffmpeg versions). Raises IngestRejected for an unusable file. Safe to re-run: outputs are
    written to `.part` files and renamed, so a killed run leaves no half-written `video.mp4`.
    """
    timings: dict[str, float] = {}
    t0 = time.monotonic()

    def lap(name: str, since: float) -> float:
        now = time.monotonic()
        timings[name] = round(now - since, 3)
        return now

    size = source.stat().st_size
    check_size(size, max_bytes)
    check_disk(size, out_dir, cfg)
    progress(0.0, "Reading video details")
    t = time.monotonic()
    probe = probe_raw(source, cfg)
    streams, duration = policy.validate_probe(
        probe, decoders=available_decoders(), min_duration_s=cfg.min_duration_s, max_duration_s=cfg.max_duration_s
    )
    decision = policy.decide(streams.video, streams.audio)
    warnings = policy.source_warnings(streams, cfg.sync_tolerance_s)
    t = lap("probe", t)

    video, audio, thumb = out_dir / VIDEO_NAME, out_dir / AUDIO_NAME, out_dir / THUMB_NAME
    video_part, audio_part = out_dir / (VIDEO_NAME + ".part"), out_dir / (AUDIO_NAME + ".part")
    label = "Copying video" if decision.video == "copy" and decision.audio == "copy" else "Converting video"
    _run(video_args(source, video_part, streams, decision, cfg), cfg, duration,
         lambda f: progress(min(0.8, 0.8 * (f or 0.0)), label))
    os.replace(video_part, video)
    t = lap("video", t)

    # audio.wav is derived from video.mp4 so the transcript timeline equals the player's timeline.
    _run(audio_args(video, audio_part), cfg, duration, lambda f: progress(min(0.95, 0.8 + 0.15 * (f or 0.0)), "Extracting audio for transcription"))
    os.replace(audio_part, audio)
    t = lap("audio", t)

    progress(0.95, "Checking the result")
    measurements = verify_outputs(video, audio, duration, cfg)
    if abs(measurements["audio_wav_duration_s"] - measurements["video_mp4_duration_s"]) > cfg.av_mismatch_warn_s:
        warnings.append({"code": "AV_DURATION_MISMATCH",
                         "detail": f"audio.wav {measurements['audio_wav_duration_s']} s vs video.mp4 {measurements['video_mp4_duration_s']} s"})
    mean = mean_volume_db(audio)
    if mean is not None and mean < cfg.silence_warn_dbfs:
        warnings.append({"code": "AUDIO_NEAR_SILENT", "detail": f"mean volume {mean:.1f} dBFS"})
    t = lap("verify", t)

    progress(0.97, "Saving thumbnail")
    _thumbnail(video, thumbnail_src, thumb, measurements["video_mp4_duration_s"], cfg)
    lap("thumbnail", t)
    timings["total"] = round(time.monotonic() - t0, 3)
    progress(1.0, "Done")
    return {
        "normaliser_version": NORMALISER_VERSION,
        "ffmpeg_version": ffmpeg_version(),
        "probe": policy.probe_summary(probe, streams, duration),
        "decision": {"video": decision.video, "audio": decision.audio, "reasons": decision.reasons},
        "warnings": warnings,
        "timings_s": timings,
        "verify": measurements,
    }
