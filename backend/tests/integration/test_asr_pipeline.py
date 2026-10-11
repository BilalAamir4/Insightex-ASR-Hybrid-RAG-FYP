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
    assert [s.name for s in job1.stages] == ["fetch", "normalise", "asr", "index"]

    same, none = run_file_job(clip, settings, conn, language="hindi")
    assert same.deduplicated and same.job_id is None and none is None
    assert len(fake_asr[0].calls) == 1

    second, job2 = run_file_job(clip, settings, conn, language="english")
    assert job2.status == "succeeded", job2.error
    assert second.workspace_id == first.workspace_id and not second.deduplicated
    assert [s.status for s in job2.stages][1:] == ["cached", "succeeded", "succeeded"]
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
    assert [s.status for s in job.stages] == ["cached", "cached", "succeeded", "succeeded"], [s.error for s in job.stages]


# One case per stage that has settings (the upload `fetch` stage's only input is the file's hash: a different file is a
# different lecture). Each setting is one the stage's cache key must contain; re-adding the lecture with it changed must
# queue a job instead of reporting "already done".
CHANGES = {
    "normalise.preset": {"ingest": {"transcode": {"preset": "medium"}}},
    "normalise.crf": {"ingest": {"transcode": {"crf": 20}}},
    "normalise.thumbnail": {"ingest": {"thumbnail": {"quality": 5}}},
    "normalise.sync_tolerance_s": {"ingest": {"verify": {"sync_tolerance_s": 0.2}}},
    "normalise.silence_warn_dbfs": {"ingest": {"silence_warn_dbfs": -40}},
    "normalise.av_mismatch_warn_s": {"ingest": {"verify": {"av_mismatch_warn_s": 2.0}}},
    "normalise.keep_original": {"ingest": {"file": {"keep_original": True}}},
    "asr.beam_size": {"asr": {"transcribe": {"beam_size": 3}}},
    "asr.model_revision": {"asr": {"model_revision": "0" * 40}},
    "asr.compute_type": {"asr": {"compute_type": "int8_float16"}},
    "index.window_s": {"index": {"window_s": 20}},
    "index.stride_s": {"index": {"stride_s": 15}},
    "index.snap_to_segments": {"index": {"snap_to_segments": True}},
    "index.max_seq_length": {"index": {"max_seq_length": 512}},
    "index.batch_size": {"index": {"batch_size": 8}},
    "index.dtype": {"index": {"dtype": "float32"}},
    "index.model_revision": {"index": {"model_revision": "0" * 40}},
    "index.model_repo": {"index": {"model_repo": "BAAI/bge-m3-other"}},
    "index.device": {"index": {"device": "cpu"}},
}


@pytest.mark.parametrize("name", list(CHANGES))
def test_changing_a_setting_in_any_stage_key_forces_a_rebuild_on_re_add(media, fake_asr, name):
    from insightex.core.config import load_settings
    from insightex.ingest.file_jobs import enqueue_file

    settings = get_settings()
    conn = open_db(settings)
    _first, job = run_file_job(media["h264_aac_mp4"], settings, conn, language="hindi")
    assert job.status == "succeeded", job.error
    again = enqueue_file(conn, settings, media["h264_aac_mp4"], language="hindi")
    assert again.deduplicated and again.job_id is None  # same settings: nothing to do
    rebuild = enqueue_file(conn, load_settings(CHANGES[name]), media["h264_aac_mp4"], language="hindi")
    assert not rebuild.deduplicated and rebuild.job_id is not None  # a job is queued, and it will rebuild from that stage on


def test_another_language_is_not_current(media, fake_asr):
    from insightex.ingest.file_jobs import enqueue_file

    settings = get_settings()
    conn = open_db(settings)
    run_file_job(media["h264_aac_mp4"], settings, conn, language="hindi")
    assert enqueue_file(conn, settings, media["h264_aac_mp4"], language="english").job_id is not None
