"""Canary tests against fixed public links, so a future run catches breakage on YouTube's or Google's side
(extractor changes, JS-runtime requirements, Drive's confirm=t workaround). Skipped by default: `pytest -m network`.

If one fails, first check that the link itself is still public before suspecting the code.
The Drive file is ~355 MB: expect a couple of minutes and that much disk under pytest's tmp dir.
"""

import os
import stat

import pytest

from insightex.ingest.engine import ingest, probe
from insightex.ingest.settings import IngestSettings

pytestmark = pytest.mark.network

YOUTUBE_URL = "https://youtu.be/a7YHpixqiUg?si=dovXyEMYwxqczXa_"
DRIVE_URL = "https://drive.google.com/file/d/1LOdr5-VQAOpBGbyl1__meBwOPDyzfWwt/view?usp=sharing"


def _check_outputs(lecture, manifest, expected_duration_s):
    assert manifest.status == "ready" and manifest.error is None
    for name in ("video.mp4", "audio.wav", "thumbnail.jpg", "manifest.json"):
        p = lecture / name
        assert p.is_file() and p.stat().st_size > 0, name
        assert stat.S_IMODE(p.stat().st_mode) == 0o644, name
    assert manifest.video["codec"] == "h264" and manifest.video["height"] <= 1080
    assert manifest.audio == {"sample_rate": 16000, "channels": 1, "codec": "pcm_s16le"}
    assert abs(manifest.duration_s - expected_duration_s) < 3
    assert os.listdir(lecture).count(".tmp") == 0


def test_youtube_probe_and_ingest(tmp_path):
    settings = IngestSettings(lectures_dir=tmp_path / "lectures")
    result = probe(YOUTUBE_URL, settings=settings)
    assert result.canonical_id == "yt:a7YHpixqiUg" and result.exists_locally is False
    assert result.normalized_url == "https://www.youtube.com/watch?v=a7YHpixqiUg"  # si= stripped
    assert abs(result.duration_s - 1140) < 3

    manifest = ingest(YOUTUBE_URL, rights_confirmed=True, settings=settings)
    _check_outputs(settings.lectures_dir / manifest.lecture_id, manifest, 1140)
    assert manifest.source_url == YOUTUBE_URL
    assert manifest.external_timestamp_url_template == "https://www.youtube.com/watch?v=a7YHpixqiUg&t={t}s"
    assert probe(YOUTUBE_URL, settings=settings).exists_locally is True


def test_drive_public_large_file_probe_and_ingest(tmp_path):
    settings = IngestSettings(lectures_dir=tmp_path / "lectures")
    result = probe(DRIVE_URL, settings=settings)
    assert result.canonical_id == "gdrive:1LOdr5-VQAOpBGbyl1__meBwOPDyzfWwt"
    assert abs(result.duration_s - 180.1) < 3

    manifest = ingest(DRIVE_URL, rights_confirmed=True, settings=settings)
    lecture = settings.lectures_dir / manifest.lecture_id
    _check_outputs(lecture, manifest, 180.1)
    # The original upload (the "source" format, ~355 MB), not one of Drive's re-encoded preview streams.
    assert (lecture / "video.mp4").stat().st_size > 100 * 1024**2
    assert manifest.external_timestamp_url_template is None
