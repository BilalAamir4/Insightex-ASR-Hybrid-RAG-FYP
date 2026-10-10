"""Synthetic media corpus for the M2 normalise tests: every clip is generated with ffmpeg lavfi sources at test time.

Nothing here is committed as binary. `Corpus.get(name)` builds a clip on first use and caches it for the
session; an encoder that this ffmpeg lacks skips the test with the encoder's name in the reason.
"""

from __future__ import annotations

import functools
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

SIZE = "320x240"
DUR = 12  # seconds; above ingest.min_duration_s (10)

# A/V sync clips: black video with a white full-frame flash from 5.0 to 5.2 s, and a 1 kHz beep over the same span.
FLASH_AT, FLASH_LEN = 5.0, 0.2


def flash_src(at: float = FLASH_AT, duration: float = 15) -> str:
    return (f"color=c=black:s={SIZE}:r=25:d={duration},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,{at},{at + FLASH_LEN})'")


FLASH_SRC = flash_src()


def beep_src(onset: float, rate: int = 48000, duration: float = 15) -> str:
    return (f"aevalsrc=exprs='if(between(t\\,{onset}\\,{onset + FLASH_LEN})\\,0.5*sin(2*PI*1000*t)\\,0)':s={rate}:d={duration}")


class EncoderMissing(Exception):
    def __init__(self, encoder: str) -> None:
        super().__init__(encoder)
        self.encoder = encoder


@functools.cache
def encoders() -> frozenset[str]:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False).stdout
    return frozenset(parts[1] for line in out.splitlines() if len(parts := line.split()) >= 2 and parts[0].startswith(("V", "A")))


def need(*names: str) -> None:
    for name in names:
        if name not in encoders():
            raise EncoderMissing(name)


def ff(*args: str | Path) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(map(str, args))}\n{proc.stderr}")


def probe(path: Path) -> dict:
    import json

    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _vsrc(size: str = SIZE, rate: int = 25, dur: float = DUR) -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={dur}"]


def _asrc(rate: int = 44100, dur: float = DUR, volume: float | None = None) -> list[str]:
    graph = f"sine=frequency=440:sample_rate={rate}:duration={dur}"
    return ["-f", "lavfi", "-i", graph + (f",volume={volume}" if volume is not None else "")]


X264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
X265 = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error"]
AAC = ["-c:a", "aac"]


class Corpus:
    """Builds clips into `root`. `get(name)` returns the path of clip `name`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, Path] = {}
        self._builders: dict[str, Callable[[], Path]] = {
            name[len("_b_"):]: getattr(self, name) for name in dir(self) if name.startswith("_b_")
        }

    def names(self) -> list[str]:
        return sorted(self._builders)

    def get(self, name: str) -> Path:
        if name not in self._cache:
            try:
                need("libx264", "aac")
                self._cache[name] = self._builders[name]()
            except EncoderMissing as exc:
                pytest.skip(f"encoder {exc.encoder} is not available in this ffmpeg")
        return self._cache[name]

    def _p(self, filename: str) -> Path:
        return self.root / filename

    # -- accepted clips ------------------------------------------------------------------------

    def _b_h264_aac_mp4(self) -> Path:
        out = self._p("h264_aac.mp4")
        ff(*_vsrc(), *_asrc(), *X264, *AAC, "-movflags", "+faststart", "-shortest", out)
        return out

    def _b_h264_aac_mp4_moov_at_end(self) -> Path:
        out = self._p("h264_aac_nofaststart.mp4")
        ff(*_vsrc(), *_asrc(), *X264, *AAC, "-shortest", out)
        return out

    def _b_h264_opus_mkv(self) -> Path:
        need("libopus")
        out = self._p("h264_opus.mkv")
        ff(*_vsrc(), *_asrc(48000), *X264, "-c:a", "libopus", "-shortest", out)
        return out

    def _b_hevc_aac_mp4(self) -> Path:
        need("libx265")
        out = self._p("hevc_aac.mp4")
        ff(*_vsrc(), *_asrc(), *X265, *AAC, "-tag:v", "hvc1", "-shortest", out)
        return out

    def _b_vp9_opus_webm(self) -> Path:
        need("libvpx-vp9", "libopus")
        out = self._p("vp9_opus.webm")
        ff(*_vsrc(), *_asrc(48000), "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "45", "-deadline", "realtime", "-cpu-used", "8",
           "-c:a", "libopus", "-shortest", out)
        return out

    def _b_av1_mkv(self) -> Path:
        out = self._p("av1.mkv")
        if "libsvtav1" in encoders():
            venc = ["-c:v", "libsvtav1", "-preset", "12", "-crf", "45", "-pix_fmt", "yuv420p"]
        elif "libaom-av1" in encoders():
            venc = ["-c:v", "libaom-av1", "-cpu-used", "8", "-crf", "45", "-b:v", "0", "-pix_fmt", "yuv420p"]
        else:
            raise EncoderMissing("libsvtav1 or libaom-av1")
        ff(*_vsrc(), *_asrc(), *venc, *AAC, "-shortest", out)
        return out

    def _b_mpeg2_interlaced_mpg(self) -> Path:
        need("mpeg2video", "mp2")
        out = self._p("interlaced.mpg")
        ff(*_vsrc(rate=25), *_asrc(48000), "-c:v", "mpeg2video", "-b:v", "2M", "-flags", "+ilme+ildct", "-top", "1",
           "-pix_fmt", "yuv420p", "-c:a", "mp2", "-shortest", out)
        return out

    def _b_wmv2_wmav2(self) -> Path:
        need("wmv2", "wmav2")
        out = self._p("legacy.wmv")
        ff(*_vsrc(), *_asrc(), "-c:v", "wmv2", "-b:v", "1M", "-c:a", "wmav2", "-shortest", out)
        return out

    def _b_h264_high10(self) -> Path:
        out = self._p("high10.mp4")
        ff(*_vsrc(), *_asrc(), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le", "-profile:v", "high10",
           *AAC, "-shortest", out)
        return out

    def _b_h264_yuv444(self) -> Path:
        out = self._p("yuv444.mp4")
        ff(*_vsrc(), *_asrc(), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv444p", "-profile:v", "high444",
           *AAC, "-shortest", out)
        return out

    def _b_odd_dimensions(self) -> Path:
        out = self._p("odd.mp4")
        ff(*_vsrc(size="321x241"), *_asrc(), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv444p",
           "-profile:v", "high444", *AAC, "-shortest", out)
        return out

    def _b_uhd_hevc(self) -> Path:
        need("libx265")
        out = self._p("uhd.mp4")
        ff(*_vsrc(size="3840x2160", rate=5), *_asrc(), *X265, *AAC, "-tag:v", "hvc1", "-shortest", out)
        return out

    def _b_vfr_h264(self) -> Path:
        out = self._p("vfr.mp4")
        graph = ("[0:v][1:v]concat=n=2:v=1:a=0[v]")
        ff(*_vsrc(rate=15, dur=6), *_vsrc(rate=30, dur=8), *_asrc(dur=14), "-filter_complex", graph, "-map", "[v]",
           "-map", "2:a", *X264, *AAC, "-fps_mode", "vfr", "-shortest", out)
        info = probe(out)["streams"]
        v = next(s for s in info if s["codec_type"] == "video")
        if v["avg_frame_rate"] == v["r_frame_rate"]:
            pytest.skip(f"ffmpeg wrote constant frame rate ({v['avg_frame_rate']}); no VFR fixture possible")
        return out

    def _flash_video_mp4(self) -> Path:
        out = self._p("flash.mp4")
        if not out.exists():
            ff("-f", "lavfi", "-i", FLASH_SRC, *X264, out)
        return out

    def _b_sync_audio_delayed_mp4(self) -> Path:
        """Container timeline: flash at 5.0 s and beep at 5.0 s, but the audio stream starts 1.5 s late (edit list)."""
        audio = self._p("beep_3_5.m4a")
        ff("-f", "lavfi", "-i", beep_src(FLASH_AT - 1.5), *AAC, audio)
        out = self._p("sync_delayed.mp4")
        ff("-i", self._flash_video_mp4(), "-itsoffset", "1.5", "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy", out)
        return out

    def _b_sync_control_mp4(self) -> Path:
        """No offsets anywhere: flash and beep both at 5.0 s on both timelines."""
        audio = self._p("beep_5_ctl.m4a")
        ff("-f", "lavfi", "-i", beep_src(FLASH_AT), *AAC, audio)
        out = self._p("sync_control.mp4")
        ff("-i", self._flash_video_mp4(), "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy", out)
        return out

    def _b_sync_video_delayed_mp4(self) -> Path:
        """Container timeline: flash and beep both at 5.0 s, but the VIDEO stream starts 1.52 s (38 frames) late."""
        video = self._p("flash_3_48.mp4")
        ff("-f", "lavfi", "-i", flash_src(FLASH_AT - 1.52), *X264, video)
        audio = self._p("beep_5_vd.m4a")
        ff("-f", "lavfi", "-i", beep_src(FLASH_AT), *AAC, audio)
        out = self._p("sync_video_delayed.mp4")
        ff("-itsoffset", "1.52", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy", out)
        return out

    def _b_sync_copied_bframes_mp4(self) -> Path:
        """H.264 with default libx264 B-frames + AAC in MP4, flash and beep at 5.0 s: eligible for copy, but its
        B-frame edit would skew a player that ignores edit lists, so the engine must transcode it (ADR-0038)."""
        out = self._p("sync_copied_bframes.mp4")
        ff("-f", "lavfi", "-i", FLASH_SRC, "-f", "lavfi", "-i", beep_src(FLASH_AT), "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", *AAC, "-movflags", "+faststart", "-shortest", out)
        return out

    def _b_sync_bframes_hevc_opus_mkv(self) -> Path:
        """HEVC + Opus without offsets (goes through the libx264 path, which uses B-frames): flash and beep at 5.0 s."""
        need("libx265", "libopus")
        video = self._p("flash_hevc_nooff.mkv")
        ff("-f", "lavfi", "-i", FLASH_SRC, *X265, video)
        audio = self._p("beep_5.opus")
        ff("-f", "lavfi", "-i", beep_src(FLASH_AT), "-c:a", "libopus", audio)
        out = self._p("sync_bframes.mkv")
        ff("-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy", out)
        return out

    def _b_sync_ts_offset_mpegts(self) -> Path:
        """Both streams start at 10 s on the file clock (flash and beep are 5 s after the start)."""
        audio = self._p("beep_5.m4a")
        ff("-f", "lavfi", "-i", beep_src(FLASH_AT), *AAC, audio)
        out = self._p("sync_offset.ts")
        ff("-i", self._flash_video_mp4(), "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy", "-output_ts_offset", "10",
           "-f", "mpegts", out)
        return out

    def _b_sync_hevc_opus_delayed_mkv(self) -> Path:
        need("libx265", "libopus")
        video = self._p("flash_hevc.mkv")
        ff("-f", "lavfi", "-i", FLASH_SRC, *X265, video)
        audio = self._p("beep_4_3.opus")
        ff("-f", "lavfi", "-i", beep_src(FLASH_AT - 0.7), "-c:a", "libopus", audio)
        out = self._p("sync_hevc_opus.mkv")
        ff("-i", video, "-itsoffset", "0.7", "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy", out)
        return out

    def _b_surround_51(self) -> Path:
        out = self._p("surround.mp4")
        ff(*_vsrc(), "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=12,"
           "pan=5.1|FL=c0|FR=c0|FC=c0|LFE=c0|BL=c0|BR=c0", *X264, *AAC, "-shortest", out)
        assert probe(out)["streams"][1]["channels"] == 6
        return out

    def _b_two_audio_and_subtitles(self) -> Path:
        srt = self._p("subs.srt")
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nhello\n\n2\n00:00:10,000 --> 00:00:12,000\nbye\n\n", encoding="utf-8")
        out = self._p("multi.mp4")
        ff(*_vsrc(), *_asrc(), "-f", "lavfi", "-i", f"sine=frequency=880:sample_rate=44100:duration={DUR}", "-i", srt,
           "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", *X264, *AAC, "-c:s", "mov_text",
           "-disposition:a:0", "0", "-disposition:a:1", "default", "-shortest", out)
        return out

    def _b_rotated_90(self) -> Path:
        base = self._p("upright.mp4")
        ff(*_vsrc(), *_asrc(), *X264, *AAC, "-shortest", base)
        out = self._p("rotated.mp4")
        ff("-display_rotation", "90", "-i", base, "-c", "copy", out)
        return out

    def _b_near_silent(self) -> Path:
        out = self._p("quiet.mp4")
        ff(*_vsrc(), *_asrc(volume=0.0005), *X264, *AAC, "-shortest", out)
        return out

    # -- rejected clips ------------------------------------------------------------------------

    def _b_audio_only_m4a(self) -> Path:
        out = self._p("audio_only.m4a")
        ff(*_asrc(), *AAC, out)
        return out

    def _b_mp3_with_cover(self) -> Path:
        need("libmp3lame", "mjpeg")
        cover = self._p("cover.jpg")
        ff("-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate=1:duration=1", "-frames:v", "1", cover)
        out = self._p("cover.mp3")
        ff(*_asrc(), "-i", cover, "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-c:v", "mjpeg",
           "-disposition:v", "attached_pic", "-id3v2_version", "3", out)
        return out

    def _b_video_only_mp4(self) -> Path:
        out = self._p("video_only.mp4")
        ff(*_vsrc(), *X264, out)
        return out

    def _b_empty_mp4(self) -> Path:
        out = self._p("empty.mp4")
        out.write_bytes(b"")
        return out

    def _b_text_as_mp4(self) -> Path:
        out = self._p("notes.mp4")
        out.write_text("These are lecture notes, not a video.\n" * 200, encoding="utf-8")
        return out

    def _b_truncated_mp4_moov_at_end(self) -> Path:
        src = self.get("h264_aac_mp4_moov_at_end")
        out = self._p("truncated.mp4")
        data = src.read_bytes()
        out.write_bytes(data[: int(len(data) * 0.6)])
        return out

    def _b_truncated_mkv(self) -> Path:
        out = self._p("whole.mkv")
        ff(*_vsrc(dur=30), *_asrc(dur=30), *X264, *AAC, "-shortest", out)
        data = out.read_bytes()
        cut = self._p("truncated.mkv")
        cut.write_bytes(data[: int(len(data) * 0.6)])
        return cut

    def _b_short_5s(self) -> Path:
        out = self._p("short.mp4")
        ff(*_vsrc(dur=5), *_asrc(dur=5), *X264, *AAC, "-shortest", out)
        return out

    def _b_long_60s_hevc_mkv(self) -> Path:
        need("libx265")
        out = self._p("long_hevc.mkv")
        ff(*_vsrc(dur=60), *_asrc(dur=60), *X265, *AAC, "-shortest", out)
        return out
