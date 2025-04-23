import json
import multiprocessing
import typing as t
import uuid
from collections import namedtuple
from contextlib import contextmanager
from typing import Any, Generator
from unittest.mock import _Call

import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from flask import Flask, template_rendered
from flask.sessions import SessionMixin
from flask.testing import FlaskClient
from flask_login import login_user
from flask_migrate import upgrade
from flask_sqlalchemy_lite import SQLAlchemy
from jinja2 import Template
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy_utils import create_database, database_exists
from testcontainers.postgres import PostgresContainer
from werkzeug.test import TestResponse

from app import create_app
from app.services.notify import Notification
from tests.conftest import FundingServiceTestClient, _precompile_templates
from tests.integration.example_models import ExampleAccountFactory, ExamplePersonFactory
from tests.integration.models import _GrantFactory, _MagicLinkFactory, _UserFactory


@pytest.fixture(scope="session")
def setup_db_container() -> Generator[None, None, None]:
    from testcontainers.core.config import testcontainers_config

    # Reduce sleep/wait time from 1 second to 0.1 seconds. We could drop this if it ever causes any problems, but shaves
    # off a little bit of time - why not.
    testcontainers_config.sleep_time = 0.1

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
def app(setup_db_container: Generator[None]) -> Generator[Flask, None, None]:
    app = create_app()
    app.config.update({"TESTING": True})
    _precompile_templates(app)
    yield app


@pytest.fixture()
def anonymous_client(app: Flask) -> FlaskClient:
    class CustomClient(FundingServiceTestClient):
        # We want to be sure that any data methods that act during the request have been
        # committed by the flask app lifecycle before continuing. Because of the way we configure
        # savepoints and rollbacks for test isolation a `flush` is considered the same as a
        # `commit` as the same session configuration is used. Calling rollback after making requests
        # to the app under test will either revert to the previous savepoint (undoing any uncommitted flushes)
        # or leave the session unchanged if it was appropriately committed. This is to be used in conjunction with
        # the `db_session` fixture.
        def open(self, *args, **kwargs) -> TestResponse:  # type: ignore[no-untyped-def]
            kwargs.setdefault("headers", {})
            kwargs["headers"].setdefault("Host", "funding.communities.gov.localhost:8080")

            response = super().open(*args, **kwargs)

            app.extensions["sqlalchemy"].session.rollback()
            return response

        @contextmanager
        def session_transaction(self, *args: t.Any, **kwargs: t.Any) -> t.Iterator[SessionMixin]:
            kwargs.setdefault("headers", {})
            kwargs["headers"].setdefault("Host", "funding.communities.gov.localhost:8080")

            with super().session_transaction(*args, **kwargs) as sess:
                yield sess

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
    request.node.add_marker(pytest.mark.fail_slow("250ms"))


@pytest.fixture(scope="function", autouse=True)
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


_Factories = namedtuple("_Factories", ["grant", "user", "magic_link"])


@pytest.fixture(scope="function")
def factories(db_session: Session) -> _Factories:
    return _Factories(grant=_GrantFactory, user=_UserFactory, magic_link=_MagicLinkFactory)


_ExampleFactories = namedtuple("_ExampleFactories", ["person", "account"])


@pytest.fixture(scope="function")
def example_factories() -> _ExampleFactories:
    return _ExampleFactories(person=ExamplePersonFactory, account=ExampleAccountFactory)


@pytest.fixture(scope="function")
def templates_rendered(app: Flask) -> Generator[list[tuple[Template, dict[str, Any]]]]:
    recorded = []

    def record(sender: Flask, template: Template, context: dict[str, Any], **extra: dict[str, Any]) -> None:
        recorded.append((template, context))

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


@pytest.fixture(scope="function")
def mock_notification_service_calls(mocker: MockerFixture) -> Generator[list[_Call], None, None]:
    calls = []

    def _track_notification(*args, **kwargs):  # type: ignore
        calls.append(mocker.call(*args, **kwargs))
        return Notification(id=uuid.uuid4())

    mocker.patch(
        "app.services.notify.NotificationService._send_email",
        side_effect=_track_notification,
    )

    yield calls


@pytest.fixture()
def authenticated_client(
    anonymous_client: FlaskClient, factories: _Factories, request: FixtureRequest
) -> Generator[FlaskClient, None, None]:
    email_mark = request.node.get_closest_marker("authenticate_as")
    email = email_mark.args[0] if email_mark else "test@communities.gov.uk"

    user = factories.user.create(email=email)

    login_user(user)

    yield anonymous_client
