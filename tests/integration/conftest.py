import json
import multiprocessing
from collections import namedtuple
from typing import Generator

import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from flask import Flask
from flask.testing import FlaskClient
from flask_migrate import upgrade
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy.orm import Session
from sqlalchemy_utils import create_database, database_exists
from testcontainers.postgres import PostgresContainer
from werkzeug.test import TestResponse

from app import create_app
from tests.integration.example_models import ExampleAccountFactory, ExamplePersonFactory
from tests.integration.models import _GrantFactory


@pytest.fixture(scope="session")
def setup_db_container() -> Generator[None, None, None]:
    test_postgres = PostgresContainer("postgres:16")
    test_postgres.start()

    monkeypatch = MonkeyPatch()
    with monkeypatch.context():
        monkeypatch.setenv("DATABASE_HOST", test_postgres.get_container_host_ip())
        monkeypatch.setenv("DATABASE_PORT", test_postgres.get_exposed_port(5432))
        monkeypatch.setenv("DATABASE_NAME", test_postgres.dbname)
        monkeypatch.setenv(
            "DATABASE_SECRET", json.dumps({"username": test_postgres.username, "password": test_postgres.password})
        )

        yield test_postgres.get_connection_url()

    test_postgres.stop()


@pytest.fixture(scope="session")
def db(setup_db_container: Generator[None], app: Flask) -> Generator[SQLAlchemy, None, None]:
    with app.app_context():
        no_db = not database_exists(app.config["SQLALCHEMY_ENGINES"]["default"])

        if no_db:
            create_database(app.config["SQLALCHEMY_ENGINES"]["default"])

        # Run alembic migrations. We do this is a separate python process because it loads and executes a bunch
        # of code from app/common/data/migrations/env.py. This does things like set up loggers, which interferes with
        # the `caplog` fixture, and possibly has some other unexpected side effects.
        ctx = multiprocessing.get_context("fork")  # spawn subprocess via fork, so it retains configuration/etc.
        proc = ctx.Process(target=upgrade)
        proc.start()
        proc.join()

    yield app.extensions["sqlalchemy"]

    with app.app_context():
        for engine in app.extensions["sqlalchemy"].engines.values():
            engine.dispose()


@pytest.fixture(scope="session")
def app(setup_db_container: Generator[SQLAlchemy]) -> Generator[Flask, None, None]:
    app = create_app()
    app.config.update({"TESTING": True})
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    class CustomClient(FlaskClient):
        # We want to be sure that any data methods that act during the request have been
        # committed by the flask app lifecycle before continuing. Because of the way we configure
        # savepoints and rollbacks for test isolation a `flush` is considered the same as a
        # `commit` as the same session configuration is used. Calling rollback after making requests
        # to the app under test will either revert to the previous savepoint (undoing any uncommitted flushes)
        # or leave the session unchanged if it was appropriately committed. This is to be used in conjunction with
        # the `db_session` fixture.
        def open(self, *args, **kwargs) -> TestResponse:  # type: ignore[no-untyped-def]
            response = super().open(*args, **kwargs)

            app.extensions["sqlalchemy"].session.rollback()
            return response

    app.test_client_class = CustomClient
    client = app.test_client()
    return client


@pytest.fixture(scope="session", autouse=True)
def _integration_test_timeout(request: FixtureRequest) -> None:
    """Fail tests under `tests/integration` if they take 'too long', to encourage us to maintain tests that are
    reasonably fast here.

    These tests may talk over the network (eg to the DB), so we need to make some allowance for that, but they should
    still be able to be fairly fast.
    """
    request.node.add_marker(pytest.mark.fail_slow("400ms"))


@pytest.fixture(scope="function")
def db_session(app: Flask, db: SQLAlchemy) -> Generator[Session, None, None]:
    # Set up a DB session that is fully isolated for each specific test run. We override Flask-SQLAlchemy-Lite's (FSL)
    # sessionmaker configuration to use a connection with a transaction started, and configure FSL to use savepoints
    # for any flushes/commits that happen within the test. When the test finishes, this fixture will do a full rollback,
    # preventing any data leaking beyond the scope of the test.

    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()

        original_configuration = db.sessionmaker.kw.copy()
        db.sessionmaker.configure(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield db.session

        finally:
            # Restore the original sessionmaker configuration.
            db.sessionmaker.configure(**original_configuration)

            db.session.close()
            transaction.rollback()
            connection.close()


_Factories = namedtuple("_Factories", ["grant"])


@pytest.fixture(scope="function")
def factories(db_session: Session) -> _Factories:
    return _Factories(grant=_GrantFactory)


_ExampleFactories = namedtuple("_ExampleFactories", ["person", "account"])


@pytest.fixture(scope="function")
def example_factories() -> _ExampleFactories:
    return _ExampleFactories(person=ExamplePersonFactory, account=ExampleAccountFactory)
