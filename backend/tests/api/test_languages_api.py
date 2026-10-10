"""Lecture language over HTTP and the CLI (ADR-0040): the list endpoint, rejections before queueing, display fields."""

from __future__ import annotations

import json
import os

import pytest

from insightex.ingest.cli import main as ingest_main
from insightex.jobs import store

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
BLOB = os.urandom(50_000)


def jobs_in_db(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]


def staged(settings) -> list[str]:
    d = settings.ingest.file.staging_dir
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def upload(client, language):
    headers = {"Content-Type": "application/octet-stream", "Content-Length": str(len(BLOB)),
               "X-Insightex-Rights-Confirmed": "true", "X-Insightex-Filename": "a.mp4"}
    if language is not None:
        headers["X-Insightex-Language"] = language
    return client.post("/api/ingest/upload", content=BLOB, headers=headers)


# -- GET /api/languages --------------------------------------------------------------------------------


def test_language_list_is_grouped_and_sorted(client):
    body = client.get("/api/languages").json()
    tested, untested = body["groups"]
    assert (tested["tier"], tested["label"]) == ("tested", "Tested")
    assert tested["languages"] == [{"id": "hindi", "label": "Hindi (including Hindi-English mixed)", "tier": "tested"}]
    assert (untested["tier"], untested["label"]) == ("untested", "Not tested — transcription quality unknown")
    labels = [lang["label"] for lang in untested["languages"]]
    assert labels == sorted(labels, key=str.casefold) and "English" in labels and "Urdu" in labels
    assert "hindi" not in [lang["id"] for lang in untested["languages"]]
    assert all(set(lang) == {"id", "label", "tier"} and lang["tier"] == "untested" for lang in untested["languages"])


# -- rejected before anything is queued ----------------------------------------------------------------


@pytest.mark.parametrize(("language", "code"), [(None, "MISSING_LANGUAGE"), ("", "MISSING_LANGUAGE"),
                                                ("klingon", "UNKNOWN_LANGUAGE"), (7, "UNKNOWN_LANGUAGE")])
def test_link_without_a_valid_language_is_400_and_nothing_is_enqueued(client, conn, language, code):
    body = {"url": YT, "rights_confirmed": True}
    if language is not None:
        body["language"] = language
    r = client.post("/api/ingest/link", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == code
    assert r.json()["error"]["message"]
    if code == "UNKNOWN_LANGUAGE" and isinstance(language, str):
        assert language in r.json()["error"]["message"]
    assert jobs_in_db(conn) == 0


@pytest.mark.parametrize(("language", "code"), [(None, "MISSING_LANGUAGE"), ("  ", "MISSING_LANGUAGE"),
                                                ("klingon", "UNKNOWN_LANGUAGE")])
def test_upload_without_a_valid_language_is_400_before_the_body_and_stages_nothing(client, conn, app_settings, language, code):
    r = upload(client, language)
    assert r.status_code == 400 and r.json()["error"]["code"] == code
    assert r.headers["connection"] == "close"
    assert jobs_in_db(conn) == 0 and staged(app_settings) == []


@pytest.mark.parametrize(("args", "code"), [([], "MISSING_LANGUAGE"), (["--language", "klingon"], "UNKNOWN_LANGUAGE")])
def test_cli_without_a_valid_language_exits_2_and_queues_nothing(tmp_path, capsys, conn, app_settings, args, code):
    video = tmp_path / "v.mp4"
    video.write_bytes(BLOB)
    for command in (["ingest", YT, "--confirm-rights"], ["ingest-file", str(video), "--confirm-rights"]):
        assert ingest_main([*command, *args]) == 2
        err = json.loads(capsys.readouterr().err.splitlines()[0])
        assert err["error"]["code"] == code
    assert jobs_in_db(conn) == 0 and staged(app_settings) == []


# -- stored and shown ----------------------------------------------------------------------------------


def test_language_is_stored_in_the_job_and_shown_with_its_current_tier(client, conn):
    job_id = client.post("/api/ingest/link", json={"url": YT, "rights_confirmed": True, "language": "english"}).json()["job_id"]
    assert store.get_job(conn, job_id).payload["language"] == "english"
    doc = client.get(f"/api/jobs/{job_id}").json()
    assert doc["language"] == {"id": "english", "label": "English", "tier": "untested"}
    assert doc["warnings"] == []
    assert client.get("/api/jobs").json()[0]["language"]["id"] == "english"


def test_upload_stores_the_language(client, conn):
    job_id = upload(client, "hindi").json()["job_id"]
    assert store.get_job(conn, job_id).payload["language"] == "hindi"


def test_same_link_in_another_language_is_a_new_job(client):
    first = client.post("/api/ingest/link", json={"url": YT, "rights_confirmed": True, "language": "hindi"}).json()
    again = client.post("/api/ingest/link", json={"url": YT, "rights_confirmed": True, "language": "hindi"}).json()
    other = client.post("/api/ingest/link", json={"url": YT, "rights_confirmed": True, "language": "urdu"}).json()
    assert again["deduplicated"] and again["job_id"] == first["job_id"]
    assert not other["deduplicated"] and other["job_id"] != first["job_id"]


def test_lecture_without_a_transcript_has_language_null(client, make_lecture):
    lecture_id = make_lecture()
    assert client.get(f"/api/lectures/{lecture_id}").json()["language"] is None
    assert client.get("/api/lectures").json()["lectures"][0]["language"] is None


def _add_transcript(workspaces, lecture_id, language_id, key="c" * 16):
    asr = workspaces.stage_dir(lecture_id, "asr", key)
    asr.mkdir(parents=True)
    (asr / "transcript.json").write_text("{}")
    (asr / "transcript.vtt").write_text("WEBVTT\n")
    workspaces.record_stage(lecture_id, "asr", key, 1.0, ["transcript.json", "transcript.vtt"],
                            extra={"language": {"id": language_id, "whisper_language": "x"}, "warnings": []})


def test_lecture_language_comes_from_the_manifest_with_the_current_tier(client, make_lecture, workspaces, app_settings,
                                                                       tmp_path, monkeypatch):
    lecture_id = make_lecture()
    _add_transcript(workspaces, lecture_id, "english")
    assert client.get(f"/api/lectures/{lecture_id}").json()["language"] == {"id": "english", "label": "English",
                                                                            "tier": "untested"}
    # Promoting english in the config changes what existing lectures show, with no reprocessing.
    text = app_settings.asr.languages_file.read_text(encoding="utf-8").replace(
        '  - id: english\n    label: "English"\n    whisper_language: "en"\n    tier: untested',
        '  - id: english\n    label: "English"\n    whisper_language: "en"\n    tier: tested\n    evidence: ADR-9999')
    promoted = tmp_path / "promoted.yaml"
    promoted.write_text(text, encoding="utf-8")
    from fastapi.testclient import TestClient

    from insightex.api.app import create_app
    from insightex.core.config import load_settings

    settings = load_settings({"asr": {"languages_file": str(promoted)}})
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/api/lectures/{lecture_id}").json()["language"]["tier"] == "tested"
