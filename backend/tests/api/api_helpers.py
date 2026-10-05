"""Helpers shared by the API tests: a lecture builder and a fake engine runner."""

from __future__ import annotations

import threading

from insightex.core.manifest import Manifest, write_manifest

YT_URL = "https://youtu.be/dQw4w9WgXcQ"
YT_ID = "yt_dQw4w9WgXcQ"
YT_URL_2 = "https://youtu.be/aaaaaaaaaaa"
VIDEO_BYTES = bytes(range(256)) * 40  # 10240 bytes, every byte value distinguishable by offset


def make_lecture(settings, lecture_id="yt_readyvideo1", status="ready", title="Ready lecture", with_media=True):
    path = settings.lectures_dir / lecture_id
    path.mkdir(parents=True)
    kind, _, rest = lecture_id.partition("_")
    m = Manifest(lecture_id=lecture_id, canonical_id=f"{kind}:{rest}", source_type="youtube",
                 source_url="https://example.invalid/x", normalized_url="https://example.invalid/x",
                 rights_confirmed=True, title=title, duration_s=12.5,
                 external_timestamp_url_template="https://www.youtube.com/watch?v=x&t={t}s")
    if status == "ready" and with_media:
        (path / "video.mp4").write_bytes(VIDEO_BYTES)
        (path / "audio.wav").write_bytes(b"RIFF")
        (path / "thumbnail.jpg").write_bytes(b"\xff\xd8jpeg")
        m.files = {"video": "video.mp4", "audio": "audio.wav", "thumbnail": "thumbnail.jpg", "source": None}
    if status == "failed":
        m.fail("DOWNLOAD_FAILED", "nope")
    else:
        m.status = status  # set directly: tests need manifests in any state, not legal transitions
    write_manifest(path, m)
    return path


class FakeRunner:
    """Stands in for engine.ingest. Blocks on `release` so tests can observe queued/running."""

    def __init__(self):
        self.calls: list[str] = []
        self.release = threading.Event()
        self.started = threading.Event()
        self.raises: Exception | None = None
        self.block = True

    def __call__(self, url, rights_confirmed, progress_cb=None, settings=None):
        assert rights_confirmed is True
        self.calls.append(url)
        self.started.set()
        progress_cb("downloading", 0.5, "half way")
        if self.block:
            assert self.release.wait(10), "test never released the fake ingest"
        if self.raises:
            raise self.raises
        progress_cb("done", 1.0, "Ready")
