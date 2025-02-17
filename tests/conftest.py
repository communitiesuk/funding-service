import pytest

from app import create_app


@pytest.fixture(scope="session")
def app():
    app = create_app()
    app.config.update({"TESTING": True})

    yield app
