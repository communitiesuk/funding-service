import pytest
from testcontainers.postgres import PostgresContainer

from app import create_app
from app.config import Config


@pytest.fixture(scope="session")
def setup_db_container():
    test_postgres = PostgresContainer("postgres:16")
    test_postgres.start()

    # testcontainers returns a psycopg2 URI by default, but we want to use psycopg3.
    postgres_uri = test_postgres.get_connection_url().replace("+psycopg2", "+psycopg")

    # FIXME: don't mutate global config; we need isolation here somehow.
    Config.SQLALCHEMY_ENGINES["default"] = postgres_uri
    yield
    test_postgres.stop()


@pytest.fixture(scope="session")
def app(setup_db_container):
    app = create_app()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(scope="session", autouse=True)
def _integration_test_timeout(request):
    """Fail tests under `tests/integration` if they take more than 10ms, to encourage us to maintain tests that are
    reasonably fast here.

    These tests may talk over the network (eg to the DB), so we need to make some allowance for that, but they should
    still be able to be fairly fast.
    """
    request.node.add_marker(pytest.mark.fail_slow("10ms"))
