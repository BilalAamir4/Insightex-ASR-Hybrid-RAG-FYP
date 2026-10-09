"""Copy-or-transcode decision (D2) and validation order (rules 3 to 6), driven by canned ffprobe JSON. No ffmpeg."""

from __future__ import annotations

import copy

import pytest

from insightex.ingest.errors import ErrorCode, IngestRejected
from insightex.media import policy

DECODERS = {"h264", "hevc", "aac", "opus", "mp3", "vp9"}


def video(**kw):
    base = {"index": 0, "codec_type": "video", "codec_name": "h264", "profile": "High", "pix_fmt": "yuv420p",
            "width": 1280, "height": 720, "field_order": "progressive", "avg_frame_rate": "25/1",
            "r_frame_rate": "25/1", "start_time": "0.000000", "disposition": {"default": 1, "attached_pic": 0}}
    return {**base, **kw}


def audio(**kw):
    base = {"index": 1, "codec_type": "audio", "codec_name": "aac", "profile": "LC", "channels": 2,
            "sample_rate": "48000", "start_time": "0.000000", "disposition": {"default": 1}}
    return {**base, **kw}


def probe(*streams, duration="60.0"):
    fmt = {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"}
    if duration is not None:
        fmt["duration"] = duration
    return {"format": fmt, "streams": list(streams)}


def validate(p, **kw):
    args = {"decoders": DECODERS, "min_duration_s": 10, "max_duration_s": 10800, **kw}
    return policy.validate_probe(p, **args)


# -- D2: one case per condition ----------------------------------------------------------------

def test_everything_compatible_copies_both():
    d = policy.decide(video(), audio())
    assert (d.video, d.audio, d.reasons, d.deinterlace, d.downmix) == ("copy", "copy", [], False, False)


@pytest.mark.parametrize("profile", ["Constrained Baseline", "Baseline", "Main", "High"])
def test_allowed_video_profiles_copy(profile):
    assert policy.decide(video(profile=profile), audio()).video == "copy"


@pytest.mark.parametrize("pix_fmt", ["yuv420p", "yuvj420p"])
def test_allowed_pix_fmts_copy(pix_fmt):
    assert policy.decide(video(pix_fmt=pix_fmt), audio()).video == "copy"


@pytest.mark.parametrize("field_order", [None, "progressive", "unknown"])
def test_progressive_or_unknown_field_order_copies(field_order):
    v = video(field_order=field_order)
    if field_order is None:
        del v["field_order"]
    assert policy.decide(v, audio()).video == "copy"


@pytest.mark.parametrize(
    "change",
    [
        {"codec_name": "hevc"},
        {"pix_fmt": "yuv420p10le"},
        {"pix_fmt": "yuv444p"},
        {"profile": "High 10"},
        {"profile": "High 4:4:4 Predictive"},
        {"profile": None},
        {"width": 321},
        {"height": 241},
        {"field_order": "tt"},
        {"field_order": "bb"},
        {"field_order": "tb"},
        {"field_order": "bt"},
    ],
)
def test_each_video_condition_forces_a_transcode(change):
    d = policy.decide(video(**change), audio())
    assert d.video == "transcode" and d.audio == "copy" and len(d.reasons) == 1


@pytest.mark.parametrize(
    "change,downmix",
    [
        ({"codec_name": "opus"},False),
        ({"codec_name": "mp3"}, False),
        ({"profile": "HE-AAC"}, False),
        ({"profile": "LC", "channels": 6}, True),
        ({"channels": 3}, True),
        ({"sample_rate": "16000"}, False),
        ({"sample_rate": "22050"}, False),
        ({"sample_rate": "96000"}, False),
    ],
)
def test_each_audio_condition_forces_a_transcode(change, downmix):
    d = policy.decide(video(), audio(**change))
    assert d.audio == "transcode" and d.video == "copy" and len(d.reasons) == 1 and d.downmix is downmix


def test_44100_and_mono_are_copied():
    assert policy.decide(video(), audio(sample_rate="44100", channels=1)).audio == "copy"


def test_interlaced_sets_deinterlace_and_reasons_accumulate():
    d = policy.decide(video(codec_name="mpeg2video", field_order="tt"), audio(codec_name="mp2"))
    assert d.deinterlace and (d.video, d.audio) == ("transcode", "transcode") and len(d.reasons) >= 3


# -- stream choice -----------------------------------------------------------------------------

def test_cover_art_is_not_a_video_stream():
    art = video(index=1, codec_name="mjpeg", disposition={"default": 0, "attached_pic": 1})
    assert policy.choose_streams(probe(audio(index=0), art))[0] is None


def test_default_video_stream_is_preferred_and_cover_art_skipped():
    art = video(index=0, disposition={"attached_pic": 1})
    other = video(index=1, disposition={"default": 0})
    wanted = video(index=2, disposition={"default": 1})
    v, _, _ = policy.choose_streams(probe(art, other, wanted, audio(index=3)))
    assert v["index"] == 2


def test_default_audio_stream_wins_over_the_first():
    first = audio(index=1, disposition={"default": 0})
    second = audio(index=2, disposition={"default": 1})
    _, a, n = policy.choose_streams(probe(video(), first, second))
    assert a["index"] == 2 and n == 2


def test_first_audio_stream_when_none_is_default():
    first = audio(index=1, disposition={"default": 0})
    second = audio(index=2, disposition={"default": 0})
    assert policy.choose_streams(probe(video(), first, second))[1]["index"] == 1


# -- validation order (rules 3 to 6): the first failure decides the code ---------------------------

def code_of(p, **kw):
    with pytest.raises(IngestRejected) as exc:
        validate(p, **kw)
    return exc.value.code


def test_valid_probe_returns_streams_and_duration():
    streams, duration = validate(probe(video(), audio()))
    assert streams.video["index"] == 0 and streams.audio["index"] == 1 and duration == 60.0


def test_rule3_no_streams_is_not_media():
    assert code_of({"format": {"duration": "30"}, "streams": []}) == ErrorCode.NOT_A_VIDEO


def test_rule4_no_video_beats_no_audio():
    assert code_of(probe(audio())) == ErrorCode.NO_VIDEO_STREAM
    assert code_of(probe(video())) == ErrorCode.NO_AUDIO_STREAM
    assert code_of(probe()) == ErrorCode.NOT_A_VIDEO  # no streams at all is rule 3


def test_rule4_cover_art_only_is_no_video():
    art = video(index=1, codec_name="mjpeg", disposition={"attached_pic": 1})
    assert code_of(probe(audio(index=0, codec_name="mp3"), art)) == ErrorCode.NO_VIDEO_STREAM


def test_rule5_missing_decoder_beats_duration_problems():
    assert code_of(probe(video(codec_name="wmv2"), audio(), duration="1")) == ErrorCode.UNSUPPORTED_CODEC
    assert code_of(probe(video(), audio(codec_name="wmav2"), duration=None)) == ErrorCode.UNSUPPORTED_CODEC
    assert code_of(probe(video(codec_name=None), audio())) == ErrorCode.UNSUPPORTED_CODEC


@pytest.mark.parametrize("duration", [None, "0", "0.0", "nan", "N/A", "inf", "-3"])
def test_rule6_unknown_duration(duration):
    p = probe(video(), audio(), duration=duration)
    assert code_of(p) == ErrorCode.DURATION_UNKNOWN


def test_rule6_duration_falls_back_to_the_longest_chosen_stream():
    p = probe(video(duration="30.5"), audio(duration="29.0"), duration=None)
    assert validate(p)[1] == 30.5


def test_rule6_too_short_and_too_long_bounds():
    assert code_of(probe(video(), audio(), duration="9.99")) == ErrorCode.TOO_SHORT
    assert validate(probe(video(), audio(), duration="10"))[1] == 10.0
    assert validate(probe(video(), audio(), duration="10800"))[1] == 10800.0
    assert code_of(probe(video(), audio(), duration="10800.5")) == ErrorCode.TOO_LONG
    assert code_of(probe(video(), audio(), duration="40"), max_duration_s=30) == ErrorCode.TOO_LONG


def test_rejection_message_is_fixed_per_code_and_details_stay_separate():
    with pytest.raises(IngestRejected) as exc:
        validate(probe(video(), audio(), duration="3"))
    assert exc.value.message == "This video is too short to add." and "3" in exc.value.details
    assert "ffmpeg" not in exc.value.message.lower()


# -- warnings and summaries --------------------------------------------------------------------

def test_source_warnings():
    s = policy.Streams(video(avg_frame_rate="45/2", r_frame_rate="30/1", side_data_list=[{"rotation": -90}]),
                       audio(start_time="1.5"), audio_count=2)
    codes = {w["code"]: w["detail"] for w in policy.source_warnings(s, 0.1)}
    assert set(codes) == {"MULTIPLE_AUDIO_STREAMS", "VFR_SOURCE", "ROTATED", "START_OFFSET_CORRECTED"}
    assert "270" in codes["ROTATED"] and "1.500" in codes["START_OFFSET_CORRECTED"]


def test_clean_source_has_no_warnings():
    assert policy.source_warnings(policy.Streams(video(), audio(), 1), 0.1) == []


def test_probe_summary_has_the_documented_fields():
    p = probe(video(), audio())
    streams, duration = validate(p)
    summary = policy.probe_summary(p, streams, duration)
    assert summary["video"]["codec"] == "h264" and summary["audio"]["channels"] == 2
    assert summary["video_stream_index"] == 0 and summary["audio_stream_index"] == 1
    assert {"profile", "pix_fmt", "width", "height", "avg_frame_rate", "r_frame_rate", "field_order", "rotation"} <= set(summary["video"])


def test_inputs_are_not_mutated():
    p = probe(video(), audio())
    before = copy.deepcopy(p)
    validate(p)
    assert p == before


# -- ffmpeg arguments ---------------------------------------------------------------------------

def _args(vdecision, adecision, **kw):
    from pathlib import Path

    from insightex.ingest.settings import IngestSettings
    from insightex.media import engine

    streams = policy.Streams(video(index=0, **kw), audio(index=2), 1)
    d = policy.Decision(vdecision, adecision, deinterlace=kw.get("field_order") in policy.INTERLACED_FIELD_ORDERS,
                        downmix=False)
    return engine.video_args(Path("in.mkv"), Path("out.part"), streams, d, IngestSettings())


def test_arguments_never_use_make_zero():
    """ADR-0036: make_zero moved B-frame decode delay into presentation time (58 ms skew); do not bring it back."""
    for v, a in (("copy", "copy"), ("transcode", "transcode"), ("copy", "transcode"), ("transcode", "copy")):
        assert "make_zero" not in _args(v, a) and "-avoid_negative_ts" not in _args(v, a)


def test_copy_arguments_map_exactly_two_streams_and_drop_the_rest():
    args = _args("copy", "copy")
    assert args[args.index("-map") + 1] == "0:0" and "0:2" in args
    assert args.count("-map") == 2 and {"-sn", "-dn"} <= set(args)
    assert args[args.index("-map_chapters") + 1] == "-1" and "-c:v" in args and args[args.index("-c:v") + 1] == "copy"
    assert "+faststart" in args and "-vf" not in args and "-af" not in args


def test_transcode_arguments_follow_d3():
    args = _args("transcode", "transcode", field_order="tt")
    joined = " ".join(args)
    assert "-vf yadif,scale=w=-2:h='min(1080,trunc(ih/2)*2)'" in joined
    assert "-c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -profile:v high" in joined
    assert "-force_key_frames expr:gte(t,n_forced*2)" in joined and "-fps_mode vfr" in joined
    assert "-c:a aac -b:a 160k -ar 48000" in joined and "-af aresample=async=1:first_pts=0" in joined
    assert "-ac" not in args  # stereo or mono source audio is not mixed


def test_progressive_transcode_has_no_yadif_and_surround_is_downmixed():
    from pathlib import Path

    from insightex.ingest.settings import IngestSettings
    from insightex.media import engine

    assert "yadif" not in " ".join(_args("transcode", "copy"))
    streams = policy.Streams(video(), audio(channels=6), 1)
    d = policy.decide(streams.video, streams.audio)
    args = engine.video_args(Path("in"), Path("out"), streams, d, IngestSettings())
    assert args[args.index("-ac") + 1] == "2"


def test_audio_wav_is_extracted_from_video_mp4_with_padding():
    from pathlib import Path

    from insightex.media import engine

    args = engine.audio_args(Path("video.mp4"), Path("audio.wav.part"))
    assert args[:2] == ["-i", "video.mp4"] and "aresample=async=1:first_pts=0" in args
    assert args[args.index("-ac") + 1] == "1" and args[args.index("-ar") + 1] == "16000" and "pcm_s16le" in args
