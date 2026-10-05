"""ffprobe/ffmpeg wrappers. CPU only: no -hwaccel, no NVENC (the GPU is reserved for Whisper/Ollama)."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
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

REMUX_PIX_FMTS = {"yuv420p", "yuvj420p"}
MAX_TRANSCODE_FPS = 60.0
DEFAULT_FPS = 30.0

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


def ffprobe(path: Path) -> MediaInfo:
    cmd = [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path.name}", proc.stderr[-4000:])
    try:
        return parse_ffprobe_json(json.loads(proc.stdout or "{}"))
    except ValueError as exc:
        raise FFmpegError(f"ffprobe returned invalid JSON for {path.name}", proc.stdout[-2000:]) from exc


def decide_processing(info: MediaInfo, max_height: int = 1080) -> str:
    """"remux" when the file already is H.264 (8-bit 4:2:0) + AAC in an MP4/MOV container within
    max_height, else "transcode"."""
    v, a = info.video, info.audio
    if v is None or a is None:
        return "transcode"
    in_mp4 = "mp4" in info.format_name.split(",")
    display_height = v.width if v.rotation in (90, 270) else v.height
    ok = (
        in_mp4
        and v.codec == "h264"
        and (v.pix_fmt in REMUX_PIX_FMTS)
        and display_height <= max_height
        and a.codec == "aac"
    )
    return "remux" if ok else "transcode"


def transcode_fps(info: MediaInfo) -> float:
    fps = info.video.fps if info.video else None
    if not fps or fps < 1:
        return DEFAULT_FPS
    return min(fps, MAX_TRANSCODE_FPS)


def remux_args(src: Path, dst: Path) -> list[str]:
    return [
        "-i", str(src), "-map", "0:v:0", "-map", "0:a:0", "-sn", "-dn",
        "-c", "copy", "-movflags", "+faststart", "-f", "mp4", str(dst),
    ]


def transcode_args(src: Path, dst: Path, info: MediaInfo, max_height: int = 1080) -> list[str]:
    fps = transcode_fps(info)
    # ffmpeg auto-rotates on decode, so ih is the displayed height. Even dimensions for yuv420p.
    vf = f"scale=w=-2:h='trunc(min({max_height},ih)/2)*2',setsar=1"
    return [
        "-i", str(src), "-map", "0:v:0", "-map", "0:a:0", "-sn", "-dn",
        "-vf", vf,
        # Variable frame rate (phones, OBS) becomes constant: timestamps stay on the wall clock.
        "-fps_mode", "cfr", "-r", f"{fps:.3f}".rstrip("0").rstrip("."),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart", "-f", "mp4", str(dst),
    ]


def audio_args(src: Path, dst: Path) -> list[str]:
    return [
        "-i", str(src), "-map", "0:a:0", "-vn",
        "-ac", str(ASR_CHANNELS), "-ar", str(ASR_SAMPLE_RATE), "-c:a", ASR_CODEC, "-f", "wav", str(dst),
    ]


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


def run_ffmpeg(
    args: list[str],
    total_s: float | None = None,
    on_fraction: FractionCb | None = None,
    min_interval_s: float = 0.5,
) -> None:
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args]
    log.debug("running %s", cmd)
    with tempfile.TemporaryFile(mode="w+") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
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
        if proc.returncode != 0:
            err.seek(0)
            raise FFmpegError(f"ffmpeg exited with {proc.returncode}", err.read()[-4000:])
    if on_fraction:
        on_fraction(1.0)


def extract_frame_jpeg(src: Path, dst: Path, at_s: float) -> None:
    args = ["-ss", f"{max(at_s, 0):.3f}", "-i", str(src), "-frames:v", "1",
            "-vf", "scale=w='min(1280,iw)':h=-2", "-q:v", "3", "-update", "1", "-f", "image2", str(dst)]
    run_ffmpeg(args)


def image_to_jpeg(src: Path, dst: Path) -> None:
    """Convert any image ffmpeg can decode (webp, png, jpg) to JPEG."""
    run_ffmpeg(["-i", str(src), "-frames:v", "1", "-q:v", "3", "-update", "1", "-f", "image2", str(dst)])
