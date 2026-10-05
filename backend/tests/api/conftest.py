"""API fixtures: the engine replaced by a fake runner, a TestClient over a tmp lectures dir."""

from __future__ import annotations

import pytest
from api_helpers import FakeRunner
from fastapi.testclient import TestClient

from insightex.api.app import create_app


@pytest.fixture
def runner():
    r = FakeRunner()
    yield r
    r.release.set()


@pytest.fixture
def client(settings, runner):
    with TestClient(create_app(settings=settings, runner=runner)) as c:
        yield c
