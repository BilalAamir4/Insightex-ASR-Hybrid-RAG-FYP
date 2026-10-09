"""Real worker processes on media jobs: kill -9 during normalisation, and `ingest-file --wait` exit codes (ADR-0036)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from insightex.core.config import clear_settings_cache, get_settings
from insightex.ingest.cli import main
from insightex.ingest.file_jobs import enqueue_file
from insightex.jobs import store
from ingest_helpers import open_db
from media_corpus import Corpus

pytestmark = [pytest.mark.media, pytest.mark.slow]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Corpus:
    return Corpus(tmp_path_factory.mktemp("worker_corpus"))


def start_worker() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "insightex.cli", "worker"], stderr=subprocess.PIPE, text=True,
                            env=os.environ.copy())


def wait_for(predicate, timeout=60.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def leftovers(settings) -> list[str]:
    """Temp files anywhere under the data directory: *.part, *.tmp, and anything inside a .staging directory."""
    found = []
    for root in (settings.jobs.workspaces_dir, settings.ingest.file.staging_dir):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and (path.suffix in (".part", ".tmp") or ".staging" in path.parts):
                found.append(str(path))
    return found


def test_kill_dash_9_during_normalisation_then_resume(corpus, monkeypatch):
    # A slow preset keeps the ~60 s transcode running long enough to kill it mid-way; both workers use the same key.
    monkeypatch.setenv("INSIGHTEX__INGEST__TRANSCODE__PRESET", "slow")
    clear_settings_cache()
    settings = get_settings()
    conn = open_db(settings)
    result = enqueue_file(conn, settings, corpus.get("long_60s_hevc_mkv"))
    part_glob = settings.jobs.workspaces_dir / result.workspace_id / ".staging"

    first = start_worker()
    try:
        wait_for(lambda: any(p.stat().st_size > 0 for p in part_glob.glob("normalise-*/video.mp4.part")),
                 what="video.mp4.part being written")
        first.send_signal(signal.SIGKILL)
        first.wait(timeout=10)
    finally:
        if first.poll() is None:
            first.kill()
    assert store.get_job(conn, result.job_id).status == "running"
    assert not (part_glob.parent / "stages" / "normalise").exists() or not any((part_glob.parent / "stages" / "normalise").iterdir())

    second = start_worker()
    try:
        wait_for(lambda: store.get_job(conn, result.job_id).status in ("succeeded", "failed"), timeout=180, what="job to finish")
    finally:
        second.send_signal(signal.SIGTERM)
        assert second.wait(timeout=20) == 0
    job = store.get_job(conn, result.job_id)
    assert job.status == "succeeded", job.error
    assert job.attempts == 2 and [s.status for s in job.stages] == ["cached", "succeeded"]
    assert leftovers(settings) == []
    out = settings.jobs.workspaces_dir / result.workspace_id / "stages" / "normalise"
    assert (next(out.iterdir()) / "video.mp4").stat().st_size > 0


def test_cli_wait_exit_codes_and_outcome(corpus, capsys):
    worker = start_worker()
    try:
        ok = main(["ingest-file", str(corpus.get("near_silent")), "--confirm-rights", "--wait"])
        out_ok = json.loads(capsys.readouterr().out)
        rejected = main(["ingest-file", str(corpus.get("short_5s")), "--confirm-rights", "--wait"])
        out_rejected = json.loads(capsys.readouterr().out)
        again = main(["ingest-file", str(corpus.get("near_silent")), "--confirm-rights", "--wait"])
        out_again = json.loads(capsys.readouterr().out)
    finally:
        worker.send_signal(signal.SIGTERM)
        worker.wait(timeout=20)
    assert ok == 0 and out_ok["status"] == "succeeded" and out_ok["deduplicated"] is False
    assert [w["code"] for w in out_ok["warnings"]] == ["AUDIO_NEAR_SILENT"]
    assert rejected == 2 and out_rejected["status"] == "rejected" and out_rejected["code"] == "TOO_SHORT"
    assert "too short" in out_rejected["message"]
    assert again == 0 and out_again["deduplicated"] is True and out_again["job_id"] is None
