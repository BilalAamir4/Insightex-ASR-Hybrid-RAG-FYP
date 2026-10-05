"""Engine behaviour with fake sources (no network) and real ffmpeg on synthetic clips."""

import json
import os
import shutil
import stat
import threading
from types import SimpleNamespace

import pytest

from insightex.core.manifest import Manifest, read_manifest, write_manifest
from insightex.ingest import engine
from insightex.ingest.errors import ErrorCode, IngestError
from insightex.ingest.settings import IngestSettings
from insightex.ingest.sources.base import SourceMeta

YT = "https://youtu.be/dQw4w9WgXcQ"
LID = "yt_dQw4w9WgXcQ"


class FakeSource:
    def __init__(self, clip, meta=None, fail_download=None):
        self.clip = clip
        self.meta = meta or SourceMeta(title="Fake lecture", uploader="Teacher", duration_s=3.0)
        self.fail_download = fail_download
        self.downloads = 0

    def probe(self, parsed, settings):
        return self.meta

    def download(self, parsed, dest_dir, settings, meta, on_bytes):
        self.downloads += 1
        if self.fail_download:
            raise self.fail_download
        out = dest_dir / f"source{self.clip.suffix}"
        shutil.copyfile(self.clip, out)
        size = out.stat().st_size
        on_bytes(size // 2, size)
        on_bytes(size, size)
        return out


@pytest.fixture
def use_source(monkeypatch):
    def install(src, kind="youtube"):
        monkeypatch.setitem(engine.SOURCES, kind, SimpleNamespace(probe=src.probe, download=src.download))
        return src
    return install


def _files(settings):
    return sorted(p.name for p in (settings.lectures_dir / LID).iterdir())


def test_rights_must_be_confirmed_first(settings, use_source, media):
    src = use_source(FakeSource(media["h264_aac_mp4"]))
    for value in (False, None, "yes", 1):
        with pytest.raises(IngestError) as e:
            engine.ingest(YT, rights_confirmed=value, settings=settings)
        assert e.value.code == ErrorCode.RIGHTS_NOT_CONFIRMED
    assert src.downloads == 0 and not settings.lectures_dir.exists()


def test_remux_end_to_end(settings, use_source, media):
    use_source(FakeSource(media["h264_aac_mp4"]))
    stages = []
    m = engine.ingest(YT, rights_confirmed=True, progress_cb=lambda s, f, msg: stages.append((s, f)), settings=settings)
    assert m.status == "ready" and m.processing == "remux" and m.error is None
    assert _files(settings) == ["audio.wav", "manifest.json", "thumbnail.jpg", "video.mp4"]
    on_disk = json.loads((settings.lectures_dir / LID / "manifest.json").read_text())
    assert on_disk["status"] == "ready"
    assert on_disk["files"] == {"video": "video.mp4", "audio": "audio.wav", "thumbnail": "thumbnail.jpg", "source": None}
    assert on_disk["video"]["codec"] == "h264" and on_disk["video"]["width"] == 320
    assert on_disk["external_timestamp_url_template"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t={t}s"
    assert on_disk["source_url"] == YT and on_disk["title"] == "Fake lecture" and on_disk["rights_confirmed"] is True
    seen = [s for s, _ in stages]
    assert [s for i, s in enumerate(seen) if i == 0 or seen[i - 1] != s] == list(engine.STAGES)
    assert stages[-1] == ("done", 1.0)


def test_transcode_and_keep_source(tmp_path, use_source, media):
    settings = IngestSettings(lectures_dir=tmp_path / "lectures", keep_source=True)
    use_source(FakeSource(media["hevc_vfr_mkv"]))
    m = engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert m.processing == "transcode" and m.files["source"] == "source.mkv"
    assert "source.mkv" in _files(settings)


def test_ready_lecture_returned_without_redownload(settings, use_source, media):
    src = use_source(FakeSource(media["h264_aac_mp4"]))
    first = engine.ingest(YT, rights_confirmed=True, settings=settings)
    second = engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert src.downloads == 1 and second == first
    assert engine.probe(YT, settings=settings).exists_locally is True


@pytest.mark.parametrize("status", ["probed", "downloading", "transcoding", "failed"])
def test_failed_or_interrupted_lecture_cleaned_and_retried(settings, use_source, media, status):
    path = settings.lectures_dir / LID
    (path / ".tmp").mkdir(parents=True)
    (path / ".tmp" / "source.mp4.part").write_bytes(b"half")
    (path / "video.mp4").write_bytes(b"stale")
    stale = Manifest(lecture_id=LID, canonical_id="yt:dQw4w9WgXcQ", source_type="youtube", source_url=YT,
                     normalized_url="x", rights_confirmed=True, status=status)
    write_manifest(path, stale)
    src = use_source(FakeSource(media["h264_aac_mp4"]))
    m = engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert src.downloads == 1 and m.status == "ready"
    assert _files(settings) == ["audio.wav", "manifest.json", "thumbnail.jpg", "video.mp4"]
    assert (path / "video.mp4").stat().st_size > 1000


def test_ready_manifest_with_missing_files_is_redone(settings, use_source, media):
    src = use_source(FakeSource(media["h264_aac_mp4"]))
    engine.ingest(YT, rights_confirmed=True, settings=settings)
    (settings.lectures_dir / LID / "audio.wav").unlink()
    engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert src.downloads == 2


def test_corrupt_manifest_treated_as_interrupted(settings, use_source, media):
    path = settings.lectures_dir / LID
    path.mkdir(parents=True)
    (path / "manifest.json").write_text("{not json")
    use_source(FakeSource(media["h264_aac_mp4"]))
    assert engine.ingest(YT, rights_confirmed=True, settings=settings).status == "ready"


@pytest.mark.parametrize(
    "clip,code",
    [("video_only_mp4", ErrorCode.NO_AUDIO_STREAM), ("audio_only_m4a", ErrorCode.NOT_A_VIDEO),
     ("garbage", ErrorCode.NOT_A_VIDEO)],
)
def test_bad_media_fails_cleanly(settings, use_source, media, clip, code):
    use_source(FakeSource(media[clip]))
    with pytest.raises(IngestError) as e:
        engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert e.value.code == code
    m = read_manifest(settings.lectures_dir / LID)
    assert m.status == "failed" and m.error["code"] == code
    assert _files(settings) == ["manifest.json"]  # no half-written media, no .tmp


def test_too_long_at_probe_and_after_download(tmp_path, use_source, media):
    settings = IngestSettings(lectures_dir=tmp_path / "l", max_duration_s=2)
    use_source(FakeSource(media["h264_aac_mp4"], SourceMeta(duration_s=999)))
    with pytest.raises(IngestError) as e:
        engine.probe(YT, settings=settings)
    assert e.value.code == ErrorCode.TOO_LONG
    # Duration unknown at probe time (e.g. direct URLs): caught by ffprobe after download.
    src = use_source(FakeSource(media["h264_aac_mp4"], SourceMeta(duration_s=None)))
    with pytest.raises(IngestError) as e:
        engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert e.value.code == ErrorCode.TOO_LONG and src.downloads == 1


def test_download_error_recorded(settings, use_source, media):
    use_source(FakeSource(media["h264_aac_mp4"], fail_download=IngestError(ErrorCode.NETWORK_ERROR)))
    with pytest.raises(IngestError):
        engine.ingest(YT, rights_confirmed=True, settings=settings)
    m = read_manifest(settings.lectures_dir / LID)
    assert m.status == "failed" and m.error["code"] == "NETWORK_ERROR"


def test_unexpected_exception_is_wrapped(settings, use_source, media):
    use_source(FakeSource(media["h264_aac_mp4"], fail_download=RuntimeError("library blew up")))
    with pytest.raises(IngestError) as e:
        engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert e.value.code == ErrorCode.DOWNLOAD_FAILED
    assert "library blew up" not in e.value.message
    assert isinstance(e.value.__cause__, RuntimeError)


def test_interrupt_leaves_in_progress_status_then_retry(settings, use_source, media):
    use_source(FakeSource(media["h264_aac_mp4"], fail_download=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        engine.ingest(YT, rights_confirmed=True, settings=settings)
    assert read_manifest(settings.lectures_dir / LID).status == "downloading"
    assert not (settings.lectures_dir / LID / ".tmp").exists()
    use_source(FakeSource(media["h264_aac_mp4"]))
    assert engine.ingest(YT, rights_confirmed=True, settings=settings).status == "ready"


def test_concurrent_ingest_downloads_once(settings, use_source, media):
    src = use_source(FakeSource(media["h264_aac_mp4"]))
    results, errors = [], []

    def run():
        try:
            results.append(engine.ingest(YT, rights_confirmed=True, settings=settings))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(results) == 3 and src.downloads == 1


def test_probe_result_fields(settings, use_source, media):
    use_source(FakeSource(media["h264_aac_mp4"], SourceMeta(title="T", uploader="U", duration_s=12.0,
                                                            thumbnail_url="https://i.ytimg.com/x.jpg")))
    r = engine.probe(YT, settings=settings).to_dict()
    assert r == {"canonical_id": "yt:dQw4w9WgXcQ", "lecture_id": LID, "source_type": "youtube",
                 "normalized_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "T", "uploader": "U",
                 "duration_s": 12.0, "thumbnail_url": "https://i.ytimg.com/x.jpg", "exists_locally": False}
    assert not settings.lectures_dir.exists()  # probe writes nothing


@pytest.mark.parametrize("keep_source", [False, True])
def test_final_files_are_0644_regardless_of_umask(tmp_path, use_source, media, keep_source):
    settings = IngestSettings(lectures_dir=tmp_path / "lectures", keep_source=keep_source)
    use_source(FakeSource(media["hevc_vfr_mkv"]))  # transcode path: ffmpeg writes with the process umask
    old = os.umask(0o077)
    try:
        engine.ingest(YT, rights_confirmed=True, settings=settings)
    finally:
        os.umask(old)
    names = ["video.mp4", "audio.wav", "thumbnail.jpg", "manifest.json"] + (["source.mkv"] if keep_source else [])
    modes = {n: stat.S_IMODE((settings.lectures_dir / LID / n).stat().st_mode) for n in names}
    assert modes == {n: 0o644 for n in names}
