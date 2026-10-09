"""Real-network ingestion tests. Skipped by default (pytest -m network to run).

Links are supplied by the user through environment variables, never chosen by the test:
    INSIGHTEX_TEST_YT_URL, INSIGHTEX_TEST_DRIVE_URL, INSIGHTEX_TEST_DIRECT_URL
Optional expected error codes for links that should fail: INSIGHTEX_TEST_<NAME>_EXPECT=<CODE>.
"""

import os

import pytest
from ingest_helpers import run_link_job

from insightex.core.config import get_settings
from insightex.ingest.probe import probe
from insightex.ingest.settings import IngestSettings
from insightex.jobs.workspace import Workspaces

pytestmark = pytest.mark.network

CASES = ["YT", "DRIVE", "DIRECT"]


def _case(name):
    url = os.environ.get(f"INSIGHTEX_TEST_{name}_URL")
    if not url:
        pytest.skip(f"INSIGHTEX_TEST_{name}_URL not set")
    return url, os.environ.get(f"INSIGHTEX_TEST_{name}_EXPECT")


@pytest.mark.parametrize("name", CASES)
def test_probe_and_ingest(name):
    url, expect = _case(name)
    settings = get_settings()
    workspaces = Workspaces(settings.jobs.workspaces_dir)
    ingest_settings = IngestSettings.from_settings(settings)
    if expect:
        job = run_link_job(url, settings)
        assert job.status == "failed" and expect in (job.error or "") + "".join(s.error or "" for s in job.stages)
        return
    assert probe(url, ingest_settings, workspaces).exists_locally is False
    job = run_link_job(url, settings)
    assert job.status == "succeeded", job.error
    out = workspaces.stage_output_dir(job.workspace_id, "normalise")
    for name_ in ("video.mp4", "audio.wav", "thumbnail.jpg"):
        assert (out / name_).is_file()
    if name == "YT":
        assert probe(url, ingest_settings, workspaces).exists_locally is True
