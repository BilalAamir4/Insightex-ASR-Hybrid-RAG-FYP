"""ADR-0054 decision 1: the stage sends the request the harness builds today (harness 8) for the same window under the
final configuration, arm C4-window (the C1 Gemma run). Both go through the real OllamaModelClient into a fake Ollama
HTTP server; the /api/chat bodies (model tag, messages, format, options, keep_alive, think, truncate) must be equal.
The served digest is checked separately (decision 7) and is not part of the body. Synthetic windows only."""

from __future__ import annotations

import json
import os

import pytest
from extract_fakes import FakeOllamaHTTP
from test_extract_stage import (  # noqa: F401 - pipeline is an autouse fixture
    KIND,
    TEXTS,
    WS,
    make_env,
    pipeline,
)

from insightex.extract import harness as h
from insightex.extract import stage as extract_stage
from insightex.extract.arms import load_arms
from insightex.extract.calls import OllamaModelClient, WindowText
from insightex.extract.translation import TranslationCache
from insightex.extract.vram import VramSampler
from insightex.jobs import db, store
from insightex.jobs.runner import run_job
from insightex.jobs.workspace import Workspaces


def test_stage_requests_are_byte_identical_to_the_harness_c4_window_requests(tmp_path, monkeypatch):
    http = FakeOllamaHTTP().install(monkeypatch)
    settings = make_env()
    arms = load_arms(settings.extract.arms_file)
    arm = arms["C4-window"]
    assert (arm.model, arm.input, arm.batch_k, arm.context) == ("gemma4:e4b", "original", 1, "none")
    assert h.HARNESS_VERSION == 8

    windows = [WindowText(i, 30.0 * i, 30.0 * i + 30, t) for i, t in enumerate(TEXTS)]
    ctx = h.RunContext(settings=settings, client=OllamaModelClient(settings), cache=h.ReplyCache(tmp_path / "cache"),
                       translations=TranslationCache(tmp_path / "translations"),
                       lease=lambda purpose: __import__("contextlib").nullcontext(),
                       sampler=VramSampler(0.01, read=lambda: 1000), fresh=True)
    h.run_arm(ctx, arm, h.load_prompts(settings, arm), WS, windows, [w.window_index for w in windows])
    harness_bodies = list(http.chat_bodies)
    assert len(harness_bodies) == len(TEXTS)

    http.chat_bodies.clear()
    monkeypatch.setattr(extract_stage, "make_client",
                        lambda s: OllamaModelClient(s, keep_alive=s.extract.stage.keep_alive))
    conn = db.open_connection(settings.jobs.db_path, settings.jobs.busy_timeout_ms)
    db.migrate(conn)
    job_id = store.enqueue(conn, KIND, {}, WS)
    run_job(conn, store.claim_next(conn, os.getpid()), settings, Workspaces(settings.jobs.workspaces_dir))
    assert store.get_job(conn, job_id).status == "succeeded"
    stage_bodies = list(http.chat_bodies)

    assert len(stage_bodies) == len(harness_bodies)
    for harness_body, stage_body in zip(harness_bodies, stage_bodies, strict=True):
        for field in ("model", "messages", "format", "options", "keep_alive", "think", "truncate", "stream"):
            assert stage_body[field] == harness_body[field], field
        assert json.dumps(stage_body, sort_keys=True) == json.dumps(harness_body, sort_keys=True)
    assert stage_bodies[0]["keep_alive"] == 0 and stage_bodies[0]["model"] == "gemma4:e4b"


@pytest.mark.parametrize("keep_alive", ["10m"])
def test_the_identity_depends_on_keep_alive_being_equal(tmp_path, monkeypatch, keep_alive):
    """Decision (a) would change the stage's keep_alive; the bodies then differ in exactly that field."""
    settings = make_env({"extract": {"stage": {"keep_alive": keep_alive}}})
    assert OllamaModelClient(settings, keep_alive=settings.extract.stage.keep_alive).keep_alive == keep_alive
    assert OllamaModelClient(settings).keep_alive == settings.extract.keep_alive == 0
