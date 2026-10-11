"""Canary tests against fixed public links, so a future run catches breakage on YouTube's or Google's side
(extractor changes, JS-runtime requirements, Drive's confirm=t workaround). Skipped by default: `pytest -m network`.

If one fails, first check that the link itself is still public before suspecting the code.
The Drive file is ~355 MB: expect a couple of minutes and that much disk under pytest's tmp dir.
"""

import json
import stat
import subprocess

import pytest
from ingest_helpers import run_link_job

from insightex.core.config import get_settings
from insightex.ingest.probe import probe
from insightex.ingest.settings import IngestSettings
from insightex.jobs.workspace import Workspaces

pytestmark = pytest.mark.network

YOUTUBE_URL = "https://youtu.be/a7YHpixqiUg?si=dovXyEMYwxqczXa_"
DRIVE_URL = "https://drive.google.com/file/d/1LOdr5-VQAOpBGbyl1__meBwOPDyzfWwt/view?usp=sharing"


def _streams(path):
    """The first stream of each type in `path`, by ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    streams = {}
    for s in json.loads(out)["streams"]:
        streams.setdefault(s["codec_type"], s)
    return streams


def _check_outputs(workspaces, job, expected_duration_s):
    assert job.status == "succeeded", job.error
    out = workspaces.stage_output_dir(job.workspace_id, "normalise")
    for name in ("video.mp4", "audio.wav", "thumbnail.jpg", "normalise.json"):
        p = out / name
        assert p.is_file() and p.stat().st_size > 0, name
        assert stat.S_IMODE(p.stat().st_mode) in (0o644, 0o600, 0o664, 0o755), name
    info = json.loads((out / "normalise.json").read_text())
    assert info["schema"] == 2 and abs(info["duration_s"] - expected_duration_s) < 3
    # normalise.json describes the source (`probe`) and the checks (`verify`); the outputs' own streams come from ffprobe
    video = _streams(out / "video.mp4")["video"]
    assert video["codec_name"] == "h264" and video["height"] <= 1080
    audio = _streams(out / "audio.wav")["audio"]
    assert (audio["codec_name"], int(audio["sample_rate"]), audio["channels"]) == ("pcm_s16le", 16000, 1)
    return out


def test_youtube_probe_and_ingest():
    settings = get_settings()
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    ingest_settings = IngestSettings.from_settings(settings)
    result = probe(YOUTUBE_URL, ingest_settings, workspaces)
    assert result.canonical_id == "yt:a7YHpixqiUg" and result.exists_locally is False
    assert result.normalized_url == "https://www.youtube.com/watch?v=a7YHpixqiUg"  # si= stripped
    assert abs(result.duration_s - 1140) < 3

    job = run_link_job(YOUTUBE_URL, settings)
    assert job.workspace_id == "yt-a7YHpixqiUg"
    _check_outputs(workspaces, job, 1140)
    source = json.loads((workspaces.stage_output_dir(job.workspace_id, "fetch") / "source.json").read_text())
    assert source["url"] == YOUTUBE_URL
    assert source["external_timestamp_url_template"] == "https://www.youtube.com/watch?v=a7YHpixqiUg&t={t}s"
    assert probe(YOUTUBE_URL, ingest_settings, workspaces).exists_locally is True
    again = run_link_job(YOUTUBE_URL, settings)
    assert [s.status for s in again.stages] == ["cached"] * 4  # fetch, normalise, asr, index


def test_drive_public_large_file_probe_and_ingest():
    settings = get_settings()
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    result = probe(DRIVE_URL, IngestSettings.from_settings(settings), workspaces)
    assert result.canonical_id == "gdrive:1LOdr5-VQAOpBGbyl1__meBwOPDyzfWwt"
    assert abs(result.duration_s - 180.1) < 3

    job = run_link_job(DRIVE_URL, settings)
    assert job.workspace_id.startswith("sha256-")
    out = _check_outputs(workspaces, job, 180.1)
    # The original upload (the "source" format, ~355 MB), not one of Drive's re-encoded preview streams.
    assert (out / "video.mp4").stat().st_size > 100 * 1024**2
