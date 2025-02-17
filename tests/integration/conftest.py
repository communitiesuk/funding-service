import pytest
from testcontainers.postgres import PostgresContainer

from app import create_app
from app.config import Config


@pytest.fixture(scope="session")
def setup_db_container():
    test_postgres = PostgresContainer("postgres:16")
    test_postgres.start()

    # FIXME: don't mutate global config; we need isolation here somehow.
    Config.SQLALCHEMY_ENGINES["default"] = test_postgres.get_connection_url()
    yield
    test_postgres.stop()


@pytest.fixture(scope="session")
def app(setup_db_container):
    app = create_app()
    yield app
