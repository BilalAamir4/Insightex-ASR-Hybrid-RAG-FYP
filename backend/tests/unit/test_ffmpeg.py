import pytest

from insightex.media import ffmpeg
from insightex.media.ffmpeg import AudioStream, MediaInfo, VideoStream

MP4 = "mov,mp4,m4a,3gp,3g2,mj2"


def _info(fmt=MP4, vcodec="h264", pix="yuv420p", w=1280, h=720, acodec="aac", rot=0, fps=30.0):
    return MediaInfo(fmt, 60.0, VideoStream(vcodec, w, h, pix, fps, rot), AudioStream(acodec, 2, 44100))


@pytest.mark.parametrize(
    "info,mode",
    [
        (_info(), "remux"),
        (_info(h=1080, w=1920), "remux"),
        (_info(w=1080, h=1920, rot=90), "remux"),       # displayed 1920x1080 landscape
        (_info(h=1440, w=2560), "transcode"),
        (_info(w=1080, h=1920), "transcode"),            # portrait 1920 tall
        (_info(fmt="matroska,webm"), "transcode"),       # OBS MKV
        (_info(vcodec="hevc"), "transcode"),             # phone HEVC
        (_info(pix="yuv420p10le"), "transcode"),         # 10-bit H.264 is not browser-safe
        (_info(acodec="opus"), "transcode"),
        (_info(acodec="mp3"), "transcode"),
        (MediaInfo(MP4, 1.0, None, AudioStream("aac", 2, 44100)), "transcode"),
    ],
)
def test_decide_processing(info, mode):
    assert ffmpeg.decide_processing(info, 1080) == mode


def test_progress_line_parsing():
    assert ffmpeg.parse_progress_line("out_time_us=5000000\n", 10.0) == 0.5
    assert ffmpeg.parse_progress_line("out_time_ms=20000000", 10.0) == 1.0
    assert ffmpeg.parse_progress_line("out_time_us=N/A", 10.0) is None
    assert ffmpeg.parse_progress_line("frame=12", 10.0) is None
    assert ffmpeg.parse_progress_line("out_time_us=5000000", None) is None
    assert ffmpeg.parse_progress_line("out_time_us=-23000", 10.0) == 0.0


def test_transcode_fps_caps():
    assert ffmpeg.transcode_fps(_info(fps=29.97)) == 29.97
    assert ffmpeg.transcode_fps(_info(fps=120.0)) == 60.0
    assert ffmpeg.transcode_fps(_info(fps=None)) == 30.0


def test_parse_ffprobe_skips_cover_art():
    data = {
        "format": {"format_name": MP4, "duration": "12.5"},
        "streams": [
            {"codec_type": "video", "codec_name": "mjpeg", "width": 500, "height": 500, "disposition": {"attached_pic": 1}},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "44100"},
        ],
    }
    info = ffmpeg.parse_ffprobe_json(data)
    assert info.video is None and info.audio.codec == "aac" and info.duration_s == 12.5


def test_ffprobe_real_clips(media):
    v = ffmpeg.ffprobe(media["h264_aac_mp4"])
    assert v.video.codec == "h264" and v.audio.codec == "aac" and ffmpeg.decide_processing(v) == "remux"
    h = ffmpeg.ffprobe(media["hevc_vfr_mkv"])
    assert h.video.codec == "hevc" and "matroska" in h.format_name and ffmpeg.decide_processing(h) == "transcode"
    assert ffmpeg.ffprobe(media["video_only_mp4"]).audio is None
    assert ffmpeg.ffprobe(media["audio_only_m4a"]).video is None
    with pytest.raises(ffmpeg.FFmpegError):
        ffmpeg.ffprobe(media["garbage"])


def test_transcode_hevc_vfr_with_progress(media, tmp_path):
    src = media["hevc_vfr_mkv"]
    info = ffmpeg.ffprobe(src)
    dst = tmp_path / "out.mp4"
    fractions = []
    ffmpeg.run_ffmpeg(ffmpeg.transcode_args(src, dst, info), info.duration_s, fractions.append, min_interval_s=0)
    out = ffmpeg.ffprobe(dst)
    assert out.video.codec == "h264" and out.video.pix_fmt == "yuv420p" and out.audio.codec == "aac"
    assert ffmpeg.decide_processing(out) == "remux"
    assert fractions and fractions[-1] == 1.0
    assert abs(out.duration_s - info.duration_s) < 0.5


def test_transcode_scales_tall_video_to_even_dims(media, tmp_path):
    src = media["tall_h264_mp4"]
    info = ffmpeg.ffprobe(src)
    assert ffmpeg.decide_processing(info) == "transcode"
    dst = tmp_path / "out.mp4"
    ffmpeg.run_ffmpeg(ffmpeg.transcode_args(src, dst, info))
    out = ffmpeg.ffprobe(dst)
    assert out.video.height == 1080 and out.video.width % 2 == 0
    assert abs(out.video.width / out.video.height - 322 / 1200) < 0.01


def test_remux_and_audio(media, tmp_path):
    src = media["h264_aac_mp4"]
    dst = tmp_path / "out.mp4"
    ffmpeg.run_ffmpeg(ffmpeg.remux_args(src, dst))
    assert ffmpeg.ffprobe(dst).video.codec == "h264"
    wav = tmp_path / "a.wav"
    ffmpeg.run_ffmpeg(ffmpeg.audio_args(dst, wav))
    a = ffmpeg.ffprobe(wav)
    assert (a.audio.codec, a.audio.sample_rate, a.audio.channels) == ("pcm_s16le", 16000, 1)


def test_faststart_moov_before_mdat(media, tmp_path):
    dst = tmp_path / "out.mp4"
    ffmpeg.run_ffmpeg(ffmpeg.remux_args(media["h264_aac_mp4"], dst))
    head = dst.read_bytes()
    assert 0 <= head.find(b"moov") < head.find(b"mdat")


def test_frame_and_image_jpeg(media, tmp_path):
    jpg = tmp_path / "t.jpg"
    ffmpeg.extract_frame_jpeg(media["h264_aac_mp4"], jpg, 0.3)
    assert jpg.read_bytes()[:2] == b"\xff\xd8"
    jpg2 = tmp_path / "t2.jpg"
    ffmpeg.image_to_jpeg(jpg, jpg2)
    assert jpg2.read_bytes()[:2] == b"\xff\xd8"


def test_ffmpeg_failure_raises_with_stderr(tmp_path):
    with pytest.raises(ffmpeg.FFmpegError) as e:
        ffmpeg.run_ffmpeg(["-i", str(tmp_path / "missing.mp4"), str(tmp_path / "o.mp4")])
    assert "missing.mp4" in e.value.stderr
