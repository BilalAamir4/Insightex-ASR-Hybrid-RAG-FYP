"""API fixtures: a TestClient over the real app, with the job database and workspaces under tmp_path."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from insightex.api.app import create_app
from insightex.core.config import get_settings
from insightex.jobs import cache, db
from insightex.jobs.workspace import Workspaces


@pytest.fixture
def app_settings():
    return get_settings()


@pytest.fixture
def client(app_settings):
    with TestClient(create_app(app_settings)) as c:
        yield c


@pytest.fixture
def conn(client, app_settings):
    c = db.open_connection(app_settings.jobs.db_path, app_settings.jobs.busy_timeout_ms)
    yield c
    c.close()


@pytest.fixture
def workspaces(app_settings):
    return Workspaces(app_settings.jobs.workspaces_dir)


@pytest.fixture
def make_lecture(conn, workspaces):
    """Create a workspace that looks like a finished ingest: fetch + normalise recorded, files on disk."""

    def make(workspace_id="yt-readyvideo1", title="Ready lecture", video=b"v" * 5000, with_normalise=True):
        key_f, key_n = "a" * 16, "b" * 16
        fetch = workspaces.stage_dir(workspace_id, "fetch", key_f)
        fetch.mkdir(parents=True)
        (fetch / "source").write_bytes(b"s")
        (fetch / "source.json").write_text(json.dumps({
            "title": title, "duration_s": 61.0, "source_type": "youtube",
            "external_timestamp_url_template": "https://www.youtube.com/watch?v=readyvideo1&t={t}s",
        }))
        workspaces.record_stage(workspace_id, "fetch", key_f, 1.0, ["source", "source.json"])
        if with_normalise:
            norm = workspaces.stage_dir(workspace_id, "normalise", key_n)
            norm.mkdir(parents=True)
            (norm / "video.mp4").write_bytes(video)
            (norm / "audio.wav").write_bytes(b"a")
            (norm / "thumbnail.jpg").write_bytes(b"\xff\xd8jpeg")
            (norm / "normalise.json").write_text(json.dumps({"duration_s": 60.5}))
            workspaces.record_stage(workspace_id, "normalise", key_n, 1.0,
                                    ["video.mp4", "audio.wav", "thumbnail.jpg", "normalise.json"])
        cache.register(conn, workspace_id, "youtube", f"https://youtu.be/{workspace_id[3:]}")
        return workspace_id

    return make
