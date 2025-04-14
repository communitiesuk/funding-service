import json
from typing import Generator

import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from flask import Flask

from app import create_app
from tests.conftest import _precompile_templates


@pytest.fixture(scope="session", autouse=True)
def _unit_test_timeout(request: FixtureRequest) -> None:
    """Fail tests under `tests/unit` if they take more than 1ms, to encourage us to maintain tests that are
    very fast here.

    These tests should not need to do anything over the network and are likely to make use of mocking to keep the
    amount of code under test fairly tight, so this should not be hard to meet.
    """
    request.node.add_marker(pytest.mark.fail_slow("1ms"))


@pytest.fixture(scope="session")
def noop_db() -> Generator[None, None, None]:
    monkeypatch = MonkeyPatch()
    with monkeypatch.context():
        monkeypatch.setenv("DATABASE_HOST", "localhost")
        monkeypatch.setenv("DATABASE_PORT", "5432")
        monkeypatch.setenv("DATABASE_NAME", "db-access-not-available-for-unit-tests")
        # pragma: allowlist nextline secret
        monkeypatch.setenv("DATABASE_SECRET", json.dumps({"username": "invalid", "password": "invalid"}))
        yield


@pytest.fixture(scope="session")
def app(noop_db: Generator[None]) -> Generator[Flask, None, None]:
    app = create_app()
    app.config.update({"TESTING": True})
    _precompile_templates(app)
    yield app
