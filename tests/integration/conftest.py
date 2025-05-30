import multiprocessing
import os
import typing as t
import uuid
from collections import namedtuple
from contextlib import _GeneratorContextManager, contextmanager
from typing import Any, Generator
from unittest.mock import _Call, patch

import pytest
from _pytest.fixtures import FixtureRequest
from flask import Flask, template_rendered
from flask.sessions import SessionMixin
from flask.testing import FlaskClient
from flask_login import login_user
from flask_migrate import upgrade
from flask_sqlalchemy_lite import SQLAlchemy
from flask_wtf import FlaskForm
from jinja2 import Template
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy_utils import create_database, database_exists
from testcontainers.postgres import PostgresContainer
from werkzeug.test import TestResponse

from app import create_app
from app.common.data.types import RoleEnum
from app.extensions.record_sqlalchemy_queries import QueryInfo, get_recorded_queries
from app.services.notify import Notification
from tests.conftest import FundingServiceTestClient, _precompile_templates
from tests.integration.example_models import ExampleAccountFactory, ExamplePersonFactory
from tests.integration.models import (
    _CollectionFactory,
    _CollectionSchemaFactory,
    _FormFactory,
    _GrantFactory,
    _MagicLinkFactory,
    _OrganisationFactory,
    _QuestionFactory,
    _SectionFactory,
    _UserFactory,
    _UserRoleFactory,
)
from tests.integration.utils import TimeFreezer
from tests.types import TTemplatesRendered
from tests.utils import build_db_config


@pytest.fixture(scope="session")
def setup_db_container() -> Generator[PostgresContainer, None, None]:
    from testcontainers.core.config import testcontainers_config

    # Reduce sleep/wait time from 1 second to 0.1 seconds. We could drop this if it ever causes any problems, but shaves
    # off a little bit of time - why not.
    testcontainers_config.sleep_time = 0.1

    test_postgres = PostgresContainer("postgres:16")
    test_postgres.start()

    yield test_postgres

    test_postgres.stop()


@pytest.fixture(scope="session")
def db(setup_db_container: PostgresContainer, app: Flask) -> Generator[SQLAlchemy, None, None]:
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
def app(setup_db_container: PostgresContainer) -> Generator[Flask, None, None]:
    with patch.dict(
        os.environ,
        build_db_config(setup_db_container),
    ):
        app = create_app()

    app.config.update({"TESTING": True})
    _precompile_templates(app)
    yield app


def _validate_form_argument_to_render_template(response: TestResponse, templates_rendered: TTemplatesRendered) -> None:
    if response.headers["content-type"].startswith("text/html"):
        for _template, kwargs in templates_rendered:
            if "form" in kwargs:
                assert isinstance(kwargs["form"], FlaskForm), (
                    "The `form` argument passed to `render_template` is expected to be a FlaskForm instance. "
                    "This powers 'magic' handling of error summary rendering."
                )


@pytest.fixture()
def anonymous_client(app: Flask, templates_rendered: TTemplatesRendered) -> FlaskClient:
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
            _validate_form_argument_to_render_template(response, templates_rendered)

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

    HACK: We double the allowable runtime duration if running in CI. We've seen that github runners are a lot slower
    than local machines. If we still keep butting up against this and it feels painful, we should feel OK to revisit
    whether this is a worthwhile check to have at all.
    """
    bad_duration = request.node.get_closest_marker("fail_if_takes_longer_than_ms", 250).args[0]
    if os.getenv("CI", "false") == "true":
        bad_duration *= 2
    request.node.add_marker(pytest.mark.fail_slow(f"{bad_duration}ms"))


@pytest.fixture(scope="function", autouse=True)
def time_freezer(db_session: Session, request: FixtureRequest) -> Generator[TimeFreezer | None, None, None]:
    marker = request.node.get_closest_marker("freeze_time")
    if marker:
        fake_time = marker.args[0]
        time_freezer = TimeFreezer(fake_time, db_session)
        yield time_freezer
        time_freezer.restore_actual_time()
    else:
        yield None


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


_Factories = namedtuple(
    "_Factories",
    [
        "grant",
        "user",
        "magic_link",
        "collection_schema",
        "collection",
        "section",
        "form",
        "question",
        "organisation",
        "user_role",
    ],
)


@pytest.fixture(scope="function")
def factories(db_session: Session) -> _Factories:
    return _Factories(
        grant=_GrantFactory,
        user=_UserFactory,
        magic_link=_MagicLinkFactory,
        collection_schema=_CollectionSchemaFactory,
        collection=_CollectionFactory,
        section=_SectionFactory,
        form=_FormFactory,
        organisation=_OrganisationFactory,
        user_role=_UserRoleFactory,
        question=_QuestionFactory,
    )


_ExampleFactories = namedtuple("_ExampleFactories", ["person", "account"])


@pytest.fixture(scope="function")
def example_factories() -> _ExampleFactories:
    return _ExampleFactories(person=ExamplePersonFactory, account=ExampleAccountFactory)


@pytest.fixture(scope="function")
def templates_rendered(app: Flask) -> Generator[TTemplatesRendered]:
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


@pytest.fixture()
def authenticated_platform_admin_client(
    anonymous_client: FlaskClient, factories: _Factories, db_session: Session, request: FixtureRequest
) -> Generator[FlaskClient, None, None]:
    email_mark = request.node.get_closest_marker("authenticate_as")
    email = email_mark.args[0] if email_mark else "test@communities.gov.uk"

    user = factories.user.create(email=email)
    factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.ADMIN)
    db_session.commit()

    login_user(user)

    yield anonymous_client


@contextmanager
def _count_sqlalchemy_queries() -> Generator[list[QueryInfo], None, None]:
    queries: list[QueryInfo] = []
    num_existing_queries = len(get_recorded_queries())

    yield queries

    new_queries = get_recorded_queries()
    queries.extend(new_queries[num_existing_queries:])


@pytest.fixture
def track_sql_queries() -> t.Callable[[], _GeneratorContextManager[list[QueryInfo], None, None]]:
    return _count_sqlalchemy_queries
