import json
import os
import stat

import pytest

from insightex.core.manifest import Manifest, ManifestError, read_manifest, write_manifest


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
