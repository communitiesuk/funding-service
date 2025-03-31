import json
import multiprocessing
from typing import Generator, Type
from uuid import uuid4

import factory
import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from flask import Flask
from flask.testing import FlaskClient
from flask_migrate import upgrade
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session
from sqlalchemy_utils import create_database, database_exists
from testcontainers.postgres import PostgresContainer

from app import create_app
from app.common.data.models import Grant


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

        yield

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


@pytest.fixture(scope="session")
def app(setup_db_container: Generator[SQLAlchemy]) -> Generator[Flask, None, None]:
    app = create_app()
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture(scope="session", autouse=True)
def _integration_test_timeout(request: FixtureRequest) -> None:
    """Fail tests under `tests/integration` if they take 'too long', to encourage us to maintain tests that are
    reasonably fast here.

    These tests may talk over the network (eg to the DB), so we need to make some allowance for that, but they should
    still be able to be fairly fast.
    """
    request.node.add_marker(pytest.mark.fail_slow("20ms"))


@pytest.fixture(scope="function")
def db_session(db: SQLAlchemy) -> Generator[Session, None, None]:
    session = db.get_session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def grant_factory(db_session: Session) -> Generator[Type[factory.alchemy.SQLAlchemyModelFactory], None, None]:
    # TODO is this the right place to define this class?
    # Explore more when looking at factory boy usage in spike
    class GrantFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = Grant
            sqlalchemy_session = db_session  # the SQLAlchemy session object

        id = factory.LazyAttribute(lambda n: uuid4())  # type:ignore
        name = factory.Sequence(lambda n: "Grant %d" % n)  # type:ignore

    yield GrantFactory
