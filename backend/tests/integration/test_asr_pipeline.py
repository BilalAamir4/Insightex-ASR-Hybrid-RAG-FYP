"""The asr stage inside the real ingest_file pipeline (real ffmpeg normalise, fake transcriber).

Resubmitting the same file with another language runs ASR again; the new transcript replaces the old one and the
lecture shows the latest language (ADR-0042). The same language again is de-duplicated at submission.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from ingest_helpers import open_db, run_file_job

from insightex.api.app import create_app
from insightex.core.config import get_settings
from insightex.jobs.workspace import Workspaces

pytestmark = pytest.mark.media


def test_second_language_wins_and_one_transcript_stays_current(media, fake_asr):
    settings = get_settings()
    conn = open_db(settings)
    clip = media["h264_aac_mp4"]

    first, job1 = run_file_job(clip, settings, conn, language="hindi")
    assert job1.status == "succeeded", job1.error
    assert [s.name for s in job1.stages] == ["fetch", "normalise", "asr"]

    same, none = run_file_job(clip, settings, conn, language="hindi")
    assert same.deduplicated and same.job_id is None and none is None
    assert len(fake_asr[0].calls) == 1

    second, job2 = run_file_job(clip, settings, conn, language="english")
    assert job2.status == "succeeded", job2.error
    assert second.workspace_id == first.workspace_id and not second.deduplicated
    assert [s.status for s in job2.stages][1:] == ["cached", "succeeded"]
    assert [c.language for c in fake_asr[0].calls] == ["ur", "en"]

    ws = Workspaces(settings.jobs.workspaces_dir)
    asr_dirs = list((ws.path(first.workspace_id) / "stages" / "asr").iterdir())
    assert len(asr_dirs) == 1
    doc = json.loads((asr_dirs[0] / "transcript.json").read_text(encoding="utf-8"))
    assert doc["language"]["id"] == "english"
    assert ws.read_manifest(first.workspace_id)["stages"]["asr"]["language"]["id"] == "english"
    with TestClient(create_app(settings)) as client:
        lecture = client.get(f"/api/lectures/{first.workspace_id}").json()
    assert lecture["language"] == {"id": "english", "label": "English", "tier": "untested"}


def test_upload_resumes_after_an_interruption_during_asr(media, fake_asr):
    """normalise deletes the uploaded original (ADR-0036); a crash in asr must not strand the job."""
    from insightex.ingest.file_jobs import enqueue_file
    from insightex.jobs import store
    from insightex.jobs.runner import run_job
    from insightex.jobs.stages import WorkerStopping

    settings = get_settings()
    conn = open_db(settings)
    result = enqueue_file(conn, settings, media["h264_aac_mp4"], language="hindi")
    fake_asr[0].error = WorkerStopping()  # the worker is told to stop while ASR runs
    ws = Workspaces(settings.jobs.workspaces_dir)
    assert run_job(conn, store.claim_next(conn, 1), settings, ws) == "queued"
    assert not (ws.stage_output_dir(result.workspace_id, "fetch") / "source").exists()  # consumed by normalise
    fake_asr[0].error = None
    assert run_job(conn, store.claim_next(conn, 1), settings, ws) == "succeeded"
    job = store.get_job(conn, result.job_id)
    assert [s.status for s in job.stages] == ["cached", "cached", "succeeded"], [s.error for s in job.stages]
