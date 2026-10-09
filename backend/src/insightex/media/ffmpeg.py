"""ffprobe/ffmpeg wrappers. CPU only: no -hwaccel, no NVENC (the GPU is reserved for Whisper/Ollama)."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

log = logging.getLogger(__name__)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

ASR_SAMPLE_RATE = 16000
ASR_CHANNELS = 1
ASR_CODEC = "pcm_s16le"

# fraction in [0, 1] or None when the total is unknown
FractionCb = Callable[[float | None], None]


class FFmpegError(Exception):
    """ffmpeg/ffprobe failed; .stderr holds the tail of its log for the error log."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


@dataclass(frozen=True)
class VideoStream:
    codec: str
    width: int
    height: int
    pix_fmt: str | None
    fps: float | None
    rotation: int


@dataclass(frozen=True)
class AudioStream:
    codec: str
    channels: int | None
    sample_rate: int | None


@dataclass(frozen=True)
class MediaInfo:
    format_name: str
    duration_s: float | None
    video: VideoStream | None
    audio: AudioStream | None


def _parse_rate(rate: str | None) -> float | None:
    try:
        value = float(Fraction(rate)) if rate else None
    except (ValueError, ZeroDivisionError):
        return None
    return value if value and value > 0 else None


def _rotation(stream: dict) -> int:
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            try:
                return int(side["rotation"]) % 360
            except (TypeError, ValueError):
                pass
    try:
        return int((stream.get("tags") or {}).get("rotate", 0)) % 360
    except ValueError:
        return 0


def parse_ffprobe_json(data: dict) -> MediaInfo:
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = audio = None
    for s in streams:
        kind = s.get("codec_type")
        if kind == "video" and video is None:
            if (s.get("disposition") or {}).get("attached_pic"):
                continue  # cover art in mp3/m4a is not a video stream
            if not s.get("width") or not s.get("height"):
                continue
            video = VideoStream(
                codec=s.get("codec_name") or "unknown",
                width=int(s["width"]),
                height=int(s["height"]),
                pix_fmt=s.get("pix_fmt"),
                fps=_parse_rate(s.get("avg_frame_rate")) or _parse_rate(s.get("r_frame_rate")),
                rotation=_rotation(s),
            )
        elif kind == "audio" and audio is None:
            audio = AudioStream(
                codec=s.get("codec_name") or "unknown",
                channels=s.get("channels"),
                sample_rate=int(s["sample_rate"]) if s.get("sample_rate") else None,
            )
    try:
        duration = float(fmt["duration"])
    except (KeyError, TypeError, ValueError):
        duration = None
    return MediaInfo(format_name=fmt.get("format_name") or "", duration_s=duration, video=video, audio=audio)


def _ingest_settings(settings=None):
    """Explicit settings from the caller, else the process settings (imported late: media sits below ingest)."""
    if settings is not None:
        return settings
    from insightex.ingest.settings import IngestSettings

    return IngestSettings.current()


def ffprobe(path: Path, settings=None) -> MediaInfo:
    cmd = [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=_ingest_settings(settings).ffprobe_timeout_s, check=False)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path.name}", proc.stderr[-4000:])
    try:
        return parse_ffprobe_json(json.loads(proc.stdout or "{}"))
    except ValueError as exc:
        raise FFmpegError(f"ffprobe returned invalid JSON for {path.name}", proc.stdout[-2000:]) from exc


def parse_progress_line(line: str, total_s: float | None) -> float | None:
    """Fraction for one `-progress` line (out_time_us=..., in microseconds), else None."""
    key, _, value = line.strip().partition("=")
    if key not in ("out_time_us", "out_time_ms") or not total_s or total_s <= 0:
        return None
    try:
        us = int(value)
    except ValueError:
        return None  # "N/A" before the first frame
    return max(0.0, min(1.0, us / 1_000_000 / total_s))


class FFmpegTimeout(FFmpegError):
    """ffmpeg did not finish within its time limit and was killed."""


def run_ffmpeg(
    args: list[str],
    total_s: float | None = None,
    on_fraction: FractionCb | None = None,
    min_interval_s: float = 0.5,
    timeout_s: float | None = None,
) -> None:
    """Run ffmpeg with an argument list. Raises FFmpegError (FFmpegTimeout after `timeout_s`), with the stderr tail attached."""
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args]
    log.debug("running %s", cmd)
    with tempfile.TemporaryFile(mode="w+") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout_s, _kill) if timeout_s else None
        if timer:
            timer.daemon = True
            timer.start()
        last = 0.0
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                frac = parse_progress_line(line, total_s)
                now = time.monotonic()
                if frac is not None and on_fraction and now - last >= min_interval_s:
                    on_fraction(frac)
                    last = now
            proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        finally:
            if timer:
                timer.cancel()
        err.seek(0)
        tail = err.read()[-4000:]
        if timed_out.is_set():
            raise FFmpegTimeout(f"ffmpeg timed out after {timeout_s:.0f}s", tail)
        if proc.returncode != 0:
            raise FFmpegError(f"ffmpeg exited with {proc.returncode}", tail)
    if on_fraction:
        on_fraction(1.0)


def extract_frame_jpeg(src: Path, dst: Path, at_s: float, settings=None) -> None:
    cfg = _ingest_settings(settings)
    args = ["-ss", f"{max(at_s, 0):.3f}", "-i", str(src), "-frames:v", "1",
            "-vf", f"scale=w='min({cfg.thumb_max_width},iw)':h=-2", "-q:v", str(cfg.thumb_quality), "-update", "1", "-f", "image2", str(dst)]
    run_ffmpeg(args)


def image_to_jpeg(src: Path, dst: Path, settings=None) -> None:
    """Convert any image ffmpeg can decode (webp, png, jpg) to JPEG."""
    run_ffmpeg(["-i", str(src), "-frames:v", "1", "-q:v", str(_ingest_settings(settings).thumb_quality),
                "-update", "1", "-f", "image2", str(dst)])
