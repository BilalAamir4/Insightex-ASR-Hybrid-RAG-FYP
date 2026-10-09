"""Pure rules of the normalise engine: stream choice, the copy-or-transcode decision and probe validation (ADR-0036).

Everything here works on the JSON that `ffprobe -show_format -show_streams` prints, so it is unit-tested
with canned dictionaries and never starts a process. The engine (`media/engine.py`) runs ffmpeg.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from insightex.ingest.errors import ErrorCode, IngestRejected

VIDEO_COPY_PROFILES = {"Constrained Baseline", "Baseline", "Main", "High"}
VIDEO_COPY_PIX_FMTS = {"yuv420p", "yuvj420p"}
AUDIO_COPY_SAMPLE_RATES = {44100, 48000}
INTERLACED_FIELD_ORDERS = {"tt", "bb", "tb", "bt"}


@dataclass(frozen=True)
class Streams:
    """The two streams the engine keeps, as ffprobe stream dictionaries."""

    video: dict[str, Any]
    audio: dict[str, Any]
    audio_count: int


@dataclass(frozen=True)
class Decision:
    video: str  # "copy" | "transcode"
    audio: str
    reasons: list[str] = field(default_factory=list)
    deinterlace: bool = False
    downmix: bool = False  # transcoded audio with more than 2 channels is mixed down to stereo
    video_pad_s: float = 0.0  # video starts this many seconds after audio: hold its first frame for this long (transcode only)


def _disposition(stream: dict[str, Any], key: str) -> bool:
    return bool((stream.get("disposition") or {}).get(key))


def choose_streams(probe: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
    """(video stream, audio stream, number of audio streams); None where there is no usable stream.

    Video: the first stream that is not cover art (`attached_pic`), preferring `default`. Audio: the stream
    marked `default`, else the first.
    """
    streams = probe.get("streams") or []
    videos = [s for s in streams if s.get("codec_type") == "video" and not _disposition(s, "attached_pic")]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    video = next((s for s in videos if _disposition(s, "default")), videos[0] if videos else None)
    audio = next((s for s in audios if _disposition(s, "default")), audios[0] if audios else None)
    return video, audio, len(audios)


def _float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def duration_of(probe: dict[str, Any], chosen: list[dict[str, Any]]) -> float | None:
    """format.duration, else the longest chosen stream's duration; None if missing, zero or not a number."""
    d = _float((probe.get("format") or {}).get("duration"))
    if d is None or d <= 0:
        candidates = [x for x in (_float(s.get("duration")) for s in chosen) if x is not None]
        d = max(candidates, default=None)
    return d if d is not None and d > 0 else None


def validate_probe(
    probe: dict[str, Any],
    *,
    decoders: set[str],
    min_duration_s: float,
    max_duration_s: float,
) -> tuple[Streams, float]:
    """Rules 3 to 6 in order; the first failure raises IngestRejected. Returns the chosen streams and the duration.

    Rules 1 and 2 (size, free disk) run before the probe, rules 7 and 8 after normalising.
    """
    if not (probe.get("streams") or []):
        raise IngestRejected(ErrorCode.NOT_A_VIDEO, details="ffprobe found no streams")
    video, audio, audio_count = choose_streams(probe)
    if video is None:
        raise IngestRejected(ErrorCode.NO_VIDEO_STREAM)
    if audio is None:
        raise IngestRejected(ErrorCode.NO_AUDIO_STREAM)
    for stream in (video, audio):
        name = stream.get("codec_name")
        if not name or name not in decoders:
            raise IngestRejected(ErrorCode.UNSUPPORTED_CODEC, details=f"no decoder for {stream.get('codec_type')} codec {name!r}")
    duration = duration_of(probe, [video, audio])
    if duration is None:
        raise IngestRejected(ErrorCode.DURATION_UNKNOWN)
    if duration < min_duration_s:
        raise IngestRejected(ErrorCode.TOO_SHORT, details=f"{duration:.2f} s < {min_duration_s} s")
    if duration > max_duration_s:
        from insightex.ingest.probe import too_long_message

        raise IngestRejected(ErrorCode.TOO_LONG, too_long_message(int(max_duration_s)), f"{duration:.1f} s > {max_duration_s} s")
    return Streams(video, audio, audio_count), duration


DEFAULT_FPS = 25.0


def _rate(value: Any) -> float | None:
    """A frame rate such as "30000/1001" or "25" as a float; None if missing, zero or malformed."""
    try:
        num, _, den = str(value).partition("/")
        rate = float(num) / (float(den) if den else 1.0)
    except (ValueError, ZeroDivisionError):
        return None
    return rate if math.isfinite(rate) and rate > 0 else None


def frame_duration_s(video: dict[str, Any], cap_s: float) -> float:
    """One video frame in seconds (25 fps if the rate is unknown), never more than `cap_s` (the sync tolerance)."""
    rate = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate")) or DEFAULT_FPS
    return min(1.0 / rate, cap_s)


def decide(video: dict[str, Any], audio: dict[str, Any], frame_s: float | None = None) -> Decision:
    """D2: copy a stream only if every condition holds; `reasons` names each condition that failed.

    With `frame_s` (one video frame), a stream that starts later than the other by more than a frame is
    transcoded so that neither track of video.mp4 needs an empty edit to stay in sync (ADR-0038): late audio is
    re-encoded with leading silence, late video is re-encoded with its first frame held for the offset.
    """
    reasons: list[str] = []
    if video.get("codec_name") != "h264":
        reasons.append(f"video codec {video.get('codec_name')} is not h264")
    if video.get("pix_fmt") not in VIDEO_COPY_PIX_FMTS:
        reasons.append(f"video pix_fmt {video.get('pix_fmt')} is not yuv420p/yuvj420p")
    if video.get("profile") not in VIDEO_COPY_PROFILES:
        reasons.append(f"video profile {video.get('profile')} is not Baseline/Main/High")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width % 2 or height % 2:
        reasons.append(f"video size {width}x{height} is not even")
    field_order = video.get("field_order")
    interlaced = field_order in INTERLACED_FIELD_ORDERS
    if interlaced:
        reasons.append(f"video field_order {field_order} is interlaced")
    offset = start_time_of(audio) - start_time_of(video)  # > 0: audio starts after video
    video_pad_s = 0.0
    if frame_s is not None and -offset > frame_s:
        video_pad_s = round(-offset, 3)
        reasons.append(f"video starts {-offset:.3f} s after audio; first frame held for that time")
    video_reasons = len(reasons)

    channels = int(audio.get("channels") or 0)
    if audio.get("codec_name") != "aac":
        reasons.append(f"audio codec {audio.get('codec_name')} is not aac")
    if audio.get("profile") != "LC":
        reasons.append(f"audio profile {audio.get('profile')} is not LC")
    if channels > 2:
        reasons.append(f"audio has {channels} channels")
    sample_rate = int(_float(audio.get("sample_rate")) or 0)
    if sample_rate not in AUDIO_COPY_SAMPLE_RATES:
        reasons.append(f"audio sample rate {sample_rate} is not 44100/48000")
    if frame_s is not None and offset > frame_s:
        reasons.append(f"audio starts {offset:.3f} s after video; re-encoded with leading silence")
    return Decision(
        video="transcode" if video_reasons else "copy",
        audio="transcode" if len(reasons) > video_reasons else "copy",
        reasons=reasons,
        deinterlace=interlaced,
        downmix=channels > 2,
        video_pad_s=video_pad_s,
    )


def rotation_of(stream: dict[str, Any]) -> int:
    """Degrees from display-matrix side data or the legacy `rotate` tag; 0 when there is none."""
    for side in stream.get("side_data_list") or []:
        value = _float(side.get("rotation"))
        if value:
            return int(value) % 360
    value = _float((stream.get("tags") or {}).get("rotate"))
    return int(value) % 360 if value else 0


def start_time_of(stream: dict[str, Any]) -> float:
    return _float(stream.get("start_time")) or 0.0


def probe_summary(probe: dict[str, Any], streams: Streams, duration: float) -> dict[str, Any]:
    v, a = streams.video, streams.audio
    return {
        "container": (probe.get("format") or {}).get("format_name"),
        "duration_s": round(duration, 3),
        "video_stream_index": v.get("index"),
        "audio_stream_index": a.get("index"),
        "video": {
            "codec": v.get("codec_name"), "profile": v.get("profile"), "pix_fmt": v.get("pix_fmt"),
            "width": v.get("width"), "height": v.get("height"), "avg_frame_rate": v.get("avg_frame_rate"),
            "r_frame_rate": v.get("r_frame_rate"), "field_order": v.get("field_order"), "rotation": rotation_of(v),
            "start_time_s": start_time_of(v),
        },
        "audio": {
            "codec": a.get("codec_name"), "profile": a.get("profile"), "channels": a.get("channels"),
            "sample_rate": int(_float(a.get("sample_rate")) or 0) or None, "start_time_s": start_time_of(a),
        },
    }


def source_warnings(streams: Streams, start_tolerance_s: float) -> list[dict[str, Any]]:
    """Warnings that depend only on the probe of the source (the rest need the outputs)."""
    out: list[dict[str, Any]] = []
    v, a = streams.video, streams.audio
    if streams.audio_count > 1:
        out.append({"code": "MULTIPLE_AUDIO_STREAMS",
                    "detail": f"{streams.audio_count} audio streams; used stream index {a.get('index')}"})
    if v.get("avg_frame_rate") != v.get("r_frame_rate"):
        out.append({"code": "VFR_SOURCE", "detail": f"avg {v.get('avg_frame_rate')} vs r {v.get('r_frame_rate')}"})
    rotation = rotation_of(v)
    if rotation:
        out.append({"code": "ROTATED", "detail": f"{rotation} degrees"})
    offsets = {"video": start_time_of(v), "audio": start_time_of(a)}
    if any(abs(t) > start_tolerance_s for t in offsets.values()):
        out.append({"code": "START_OFFSET_CORRECTED",
                    "detail": ", ".join(f"{k} starts at {t:.3f} s" for k, t in offsets.items())})
    return out
