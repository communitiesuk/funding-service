import os
from typing import Generator
from unittest.mock import patch

import pytest
from _pytest.fixtures import FixtureRequest
from flask import Flask

from app import create_app
from tests.conftest import _precompile_templates
from tests.utils import build_db_config


@pytest.fixture(scope="session", autouse=True)
def _unit_test_timeout(request: FixtureRequest) -> None:
    """Fail tests under `tests/unit` if they take more than 1ms, to encourage us to maintain tests that are
    very fast here.

    These tests should not need to do anything over the network and are likely to make use of mocking to keep the
    amount of code under test fairly tight, so this should not be hard to meet.
    """
    request.node.add_marker(pytest.mark.fail_slow("1ms"))


@pytest.fixture(scope="session")
def app() -> Generator[Flask, None, None]:
    with patch.dict(os.environ, build_db_config(None)):
        app = create_app()

    app.config.update({"TESTING": True})
    _precompile_templates(app)
    yield app
