"""Shared fixtures. Media fixtures are synthetic clips generated with ffmpeg at test time (none committed)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from insightex.ingest.settings import IngestSettings


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


_SRC_V = ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=3"]
_SRC_A = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=3"]


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("media")
    clips = {
        # Already H.264 (yuv420p) + AAC in mp4: should remux.
        "h264_aac_mp4": (d / "h264_aac.mp4", [*_SRC_V, *_SRC_A, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                              "-c:a", "aac", "-shortest"]),
        # Phone-style HEVC in MKV (OBS-style container) with variable frame rate: should transcode.
        "hevc_vfr_mkv": (d / "hevc_vfr.mkv", [*_SRC_V, *_SRC_A, "-vf", "select='not(mod(n\\,3))+lt(n\\,10)'",
                                              "-fps_mode", "vfr", "-c:v", "libx265", "-x265-params", "log-level=error",
                                              "-c:a", "libopus", "-shortest"]),
        # H.264 + AAC in mp4 but taller than 1080 (and odd width): transcode to scale down.
        "tall_h264_mp4": (d / "tall.mp4", ["-f", "lavfi", "-i", "testsrc2=size=322x1200:rate=10:duration=1",
                                           "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264",
                                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]),
        "video_only_mp4": (d / "video_only.mp4", [*_SRC_V, "-c:v", "libx264", "-pix_fmt", "yuv420p"]),
        "audio_only_m4a": (d / "audio_only.m4a", [*_SRC_A, "-c:a", "aac"]),
    }
    out = {}
    for key, (path, args) in clips.items():
        _ffmpeg(*args, str(path))
        out[key] = path
    garbage = d / "garbage.mp4"
    garbage.write_bytes(os.urandom(64 * 1024))
    out["garbage"] = garbage
    return out


@pytest.fixture
def settings(tmp_path) -> IngestSettings:
    return IngestSettings(lectures_dir=tmp_path / "lectures")
