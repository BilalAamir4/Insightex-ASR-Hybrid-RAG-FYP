"""Real-network ingestion tests. Skipped by default (pytest -m network to run).

Links are supplied by the user through environment variables, never chosen by the test:
    INSIGHTEX_TEST_YT_URL, INSIGHTEX_TEST_DRIVE_URL, INSIGHTEX_TEST_DIRECT_URL
Optional expected error codes for links that should fail: INSIGHTEX_TEST_<NAME>_EXPECT=<CODE>.
"""

import os

import pytest

from insightex.ingest.engine import ingest, probe
from insightex.ingest.errors import IngestError
from insightex.ingest.settings import IngestSettings

pytestmark = pytest.mark.network

CASES = ["YT", "DRIVE", "DIRECT"]


def _case(name):
    url = os.environ.get(f"INSIGHTEX_TEST_{name}_URL")
    if not url:
        pytest.skip(f"INSIGHTEX_TEST_{name}_URL not set")
    return url, os.environ.get(f"INSIGHTEX_TEST_{name}_EXPECT")


@pytest.mark.parametrize("name", CASES)
def test_probe_and_ingest(name, tmp_path):
    url, expect = _case(name)
    settings = IngestSettings(lectures_dir=tmp_path / "lectures")
    if expect:
        with pytest.raises(IngestError) as e:
            probe(url, settings=settings)
            ingest(url, rights_confirmed=True, settings=settings)
        assert e.value.code == expect
        return
    result = probe(url, settings=settings)
    assert result.exists_locally is False
    manifest = ingest(url, rights_confirmed=True, settings=settings)
    assert manifest.status == "ready"
    lecture = settings.lectures_dir / manifest.lecture_id
    for name_ in ("video.mp4", "audio.wav", "manifest.json"):
        assert (lecture / name_).is_file()
    assert probe(url, settings=settings).exists_locally is True
