import json
import os
import stat

import pytest

from insightex.core.manifest import SCHEMA_VERSION, Manifest, ManifestError, read_manifest, write_manifest


def _m(**kw):
    base = dict(lecture_id="yt_dQw4w9WgXcQ", canonical_id="yt:dQw4w9WgXcQ", source_type="youtube",
                source_url="https://youtu.be/dQw4w9WgXcQ", normalized_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                rights_confirmed=True)
    return Manifest(**(base | kw))


def test_round_trip_and_required_fields(tmp_path):
    m = _m(title="Lecture 1", external_timestamp_url_template="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t={t}s")
    write_manifest(tmp_path, m)
    data = json.loads((tmp_path / "manifest.json").read_text())
    for key in ("lecture_id", "canonical_id", "source_type", "source_url", "normalized_url", "title", "uploader",
                "duration_s", "rights_confirmed", "status", "error", "created_at", "updated_at", "video", "files",
                "external_timestamp_url_template"):
        assert key in data
    assert data["created_at"].endswith("Z")
    assert read_manifest(tmp_path) == m


def test_atomic_write_leaves_no_temp_files(tmp_path):
    m = _m()
    for _ in range(5):
        write_manifest(tmp_path, m)
    assert sorted(os.listdir(tmp_path)) == ["manifest.json"]


def test_failed_write_keeps_previous_manifest(tmp_path, monkeypatch):
    write_manifest(tmp_path, _m(title="old"))

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("insightex.core.manifest.os.replace", boom)
    with pytest.raises(OSError):
        write_manifest(tmp_path, _m(title="new"))
    assert read_manifest(tmp_path).title == "old"
    assert sorted(os.listdir(tmp_path)) == ["manifest.json"]


def test_unreadable_manifest_is_none(tmp_path):
    assert read_manifest(tmp_path) is None
    (tmp_path / "manifest.json").write_text("{truncated")
    assert read_manifest(tmp_path) is None


def test_forward_transitions():
    m = _m()
    assert m.status == "probed"
    before = m.updated_at
    for s in ("downloading", "transcoding", "ready"):
        m.set_status(s)
        assert m.status == s
    assert m.updated_at >= before


@pytest.mark.parametrize(
    "path,bad",
    [((), "transcoding"), ((), "ready"), (("downloading",), "probed"), (("downloading", "transcoding", "ready"), "failed"),
     ((), "bogus")],
)
def test_illegal_transitions(path, bad):
    m = _m()
    for s in path:
        m.set_status(s)
    with pytest.raises(ManifestError):
        m.set_status(bad)


@pytest.mark.parametrize("path", [(), ("downloading",), ("downloading", "transcoding")])
def test_fail_from_any_in_progress_status(path):
    m = _m()
    for s in path:
        m.set_status(s)
    m.fail("DOWNLOAD_FAILED", "nope")
    assert m.status == "failed" and m.error == {"code": "DOWNLOAD_FAILED", "message": "nope"}


def test_manifest_is_0644_regardless_of_umask(tmp_path):
    old = os.umask(0o077)  # a hostile umask: the mode must come from the code, not the environment
    try:
        write_manifest(tmp_path, _m())
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "manifest.json").stat().st_mode) == 0o644


def test_v1_manifest_loads_with_processing_mapped_to_decision(tmp_path):
    v1 = {
        "lecture_id": "yt_dQw4w9WgXcQ", "canonical_id": "yt:dQw4w9WgXcQ", "source_type": "youtube",
        "source_url": "https://youtu.be/dQw4w9WgXcQ", "normalized_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "rights_confirmed": True, "status": "ready", "title": "Old", "uploader": None, "duration_s": 12.0,
        "error": None, "created_at": "2026-10-05T20:00:00Z", "updated_at": "2026-10-05T20:01:00Z",
        "video": {"codec": "h264", "width": 1920, "height": 1080, "fps": 24.0},
        "audio": {"sample_rate": 16000, "channels": 1, "codec": "pcm_s16le"},
        "processing": "transcode",
        "files": {"video": "video.mp4", "audio": "audio.wav", "thumbnail": "thumbnail.jpg", "source": None},
        "external_timestamp_url_template": None, "schema_version": 1,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(v1))
    m = read_manifest(tmp_path)
    assert m is not None and m.decision == "transcode" and m.source is None and m.title == "Old"
    assert m.schema_version == SCHEMA_VERSION == 2
    write_manifest(tmp_path, m)  # writes always produce v2, without the old key
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk["schema_version"] == 2 and on_disk["decision"] == "transcode" and "processing" not in on_disk


def test_manifest_without_schema_version_is_treated_as_v1(tmp_path):
    data = _m().to_dict() | {"processing": "remux"}
    del data["schema_version"], data["decision"], data["source"]
    (tmp_path / "manifest.json").write_text(json.dumps(data))
    m = read_manifest(tmp_path)
    assert m is not None and m.decision == "remux" and m.source is None


def test_v2_round_trip(tmp_path):
    m = _m(decision="remux", source={"codec": "h264", "width": 1920, "height": 1080, "fps": 23.976,
                                      "container": "mov,mp4,m4a,3gp,3g2,mj2"})
    write_manifest(tmp_path, m)
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk["schema_version"] == 2 and on_disk["decision"] == "remux" and "processing" not in on_disk
    assert read_manifest(tmp_path) == m
