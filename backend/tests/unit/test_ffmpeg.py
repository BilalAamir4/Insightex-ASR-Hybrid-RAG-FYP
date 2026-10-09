import pytest

from insightex.media import ffmpeg

MP4 = "mov,mp4,m4a,3gp,3g2,mj2"


def test_progress_line_parsing():
    assert ffmpeg.parse_progress_line("out_time_us=5000000\n", 10.0) == 0.5
    assert ffmpeg.parse_progress_line("out_time_ms=20000000", 10.0) == 1.0
    assert ffmpeg.parse_progress_line("out_time_us=N/A", 10.0) is None
    assert ffmpeg.parse_progress_line("frame=12", 10.0) is None
    assert ffmpeg.parse_progress_line("out_time_us=5000000", None) is None
    assert ffmpeg.parse_progress_line("out_time_us=-23000", 10.0) == 0.0


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
    assert v.video.codec == "h264" and v.audio.codec == "aac"
    h = ffmpeg.ffprobe(media["hevc_vfr_mkv"])
    assert h.video.codec == "hevc" and "matroska" in h.format_name
    assert ffmpeg.ffprobe(media["video_only_mp4"]).audio is None
    assert ffmpeg.ffprobe(media["audio_only_m4a"]).video is None
    with pytest.raises(ffmpeg.FFmpegError):
        ffmpeg.ffprobe(media["garbage"])


def test_run_ffmpeg_timeout_kills_the_process(tmp_path):
    args = ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=600", "-c:v", "libx264", "-preset", "veryslow",
            "-f", "null", "-"]
    with pytest.raises(ffmpeg.FFmpegTimeout):
        ffmpeg.run_ffmpeg(args, timeout_s=0.5)


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
