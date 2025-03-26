from typing import Generator

import pytest
from flask import Flask

from app import create_app


@pytest.fixture(scope="session")
def app() -> Generator[Flask, None, None]:
    app = create_app()
    app.config.update({"TESTING": True})

    yield app
