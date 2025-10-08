# mypy: disable-error-code="unused-ignore"

import multiprocessing
import os
import typing as t
import uuid
from contextlib import _GeneratorContextManager, contextmanager
from typing import Any, Generator
from unittest.mock import _Call, patch

import pytest
from _pytest.fixtures import FixtureRequest
from flask import Flask, abort, template_rendered
from flask.sessions import SessionMixin
from flask.typing import ResponseReturnValue
from flask_login import login_user
from flask_migrate import upgrade
from flask_sqlalchemy_lite import SQLAlchemy
from flask_wtf import FlaskForm
from jinja2 import Template
from pytest_mock import MockerFixture
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import SessionTransaction
from sqlalchemy_utils import create_database, database_exists
from testcontainers.postgres import PostgresContainer
from werkzeug.test import TestResponse

from app import create_app
from app.common.data.models_user import User
from app.common.data.types import AuthMethodEnum, RoleEnum
from app.extensions.record_sqlalchemy_queries import QueryInfo, get_recorded_queries
from app.services.notify import Notification
from tests.conftest import FundingServiceTestClient, _Factories, _precompile_templates
from tests.integration.utils import TimeFreezer
from tests.types import TemplateRenderRecord, TTemplatesRendered
from tests.utils import build_db_config


@pytest.fixture(scope="session")
def setup_db_container() -> Generator[PostgresContainer, None, None]:
    from testcontainers.core.config import testcontainers_config

    # Reduce sleep/wait time from 1 second to 0.1 seconds. We could drop this if it ever causes any problems, but shaves
    # off a little bit of time - why not.
    testcontainers_config.sleep_time = 0.1  # ty: ignore[invalid-assignment]

    test_postgres = PostgresContainer("postgres:17.5")
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

    @app.route("/_testing/403")
    def raise_403() -> ResponseReturnValue:
        return abort(403)

    @app.route("/_testing/500")
    def raise_500() -> ResponseReturnValue:
        return abort(500)

    @app.route("/_testing/sqlalchemy-not-found")
    def raise_sqlalchemy_not_found() -> ResponseReturnValue:
        # get a thing that doesn't exist
        try:
            app.extensions["sqlalchemy"].session.query(User).where(User.id == uuid.uuid4()).one()
        except Exception as e:
            if not isinstance(e, NoResultFound):
                return abort(500)
            raise e
        raise RuntimeError("query expected no results and an error, but didn't")

    app.config.update({"TESTING": True})
    _precompile_templates(app)
    yield app


def _validate_form_argument_to_render_template(response: TestResponse, templates_rendered: TTemplatesRendered) -> None:
    if response.headers["content-type"].startswith("text/html"):
        for _endpoint, render_template in templates_rendered.items():
            if "form" in render_template.context and render_template.context["form"]:
                assert isinstance(render_template.context["form"], FlaskForm), (
                    "The `form` argument passed to `render_template` is expected to be a FlaskForm instance. "
                    "This powers 'magic' handling of error summary rendering."
                )


@pytest.fixture()
def anonymous_client(app: Flask, templates_rendered: TTemplatesRendered) -> FundingServiceTestClient:
    _setup_session_clean_tracking()  # setting up listeners

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

            # WARNING: this check is unreliable if using `follow_redirects=True`. When this is set, the FlaskClient
            # will seamlessly resolve any redirects and potentially fire off multiple requests. If the first request
            # doesn't commit properly, then subsequent requests either commit or rollback, the DB session state may
            # not remain "un-clean", leading to this not triggering.
            # Addressing this properly requires a bit more depth and finick than I'm interested in us taking here, for
            # what is supposed to be a "helpful" check rather than a "rock-solid" check.
            session = app.extensions["sqlalchemy"].session
            if not session.info.get("clean", True):
                # args[0] is not always a nicely-readable thing; it might be a dict or EnvironBuilder instance.
                # But it's sort-of-ok and easy-enough to grab for now to be helpful more often than not.
                method = kwargs.get("method") or (args[0] if args else "GET")
                path = kwargs.get("path") or (args[0] if args else "/")

                raise pytest.fail(
                    f"Detected uncommitted changes in the SQLAlchemy session after handling "
                    f"{method} request to {path}. "
                    f"To ensure database consistency, wrap your request handler with @auto_commit_after_request."
                )

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
    return t.cast(CustomClient, client)


@pytest.fixture(scope="session", autouse=True)
def _integration_test_timeout(request: FixtureRequest) -> None:
    """Fail tests under `tests/integration` if they take 'too long', to encourage us to maintain tests that are
    reasonably fast here.

    These tests may talk over the network (eg to the DB), so we need to make some allowance for that, but they should
    still be able to be fairly fast.
    """
    request.node.add_marker(pytest.mark.fail_slow("3000ms", enabled="CI" not in os.environ))


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
    #
    # NOTE: this fixture is automatically used by all integration tests, and provides both an app context and a test
    # request context. So you will not need to manually create these within your integration tests.

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


@pytest.fixture(scope="function")
def templates_rendered(app: Flask) -> Generator[TTemplatesRendered]:
    recorded: TTemplatesRendered = {}

    def record(sender: Flask, template: Template, context: dict[str, Any], **extra: dict[str, Any]) -> None:
        request = context.get("request")
        if template.name and "govuk_frontend_wtf" not in template.name and request and request.endpoint:
            endpoint = request.endpoint
            entry = TemplateRenderRecord(template=template, context=context)
            if endpoint not in recorded:
                recorded[endpoint] = entry

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
def authenticated_no_role_client(
    anonymous_client: FundingServiceTestClient, factories: _Factories, request: FixtureRequest, db_session: Session
) -> Generator[FundingServiceTestClient, None, None]:
    email_mark = request.node.get_closest_marker("authenticate_as")
    email = email_mark.args[0] if email_mark else "test@communities.gov.uk"

    user = factories.user.create(email=email)

    # `login_user(user)` is what we use to catch and update a user's `last_logged_in_at_utc` by looking out for flask
    # login's `user_logged_in` signal. In our app, these `login_user(user)` calls are only done in routes that use the
    # `auto_commit_after_request` decorator, but here we're not in an existing session and would be left with a dirty
    # session after this client is used in tests, so we need to commit this change to the user before we continue.
    login_user(user)
    with anonymous_client.session_transaction() as session:
        session["auth"] = AuthMethodEnum.SSO

    anonymous_client.user = user
    db_session.commit()

    yield anonymous_client


@pytest.fixture()
def authenticated_grant_member_client(
    anonymous_client: FundingServiceTestClient, factories: _Factories, db_session: Session, request: FixtureRequest
) -> Generator[FundingServiceTestClient, None, None]:
    email_mark = request.node.get_closest_marker("authenticate_as")
    email = email_mark.args[0] if email_mark else "test2@communities.gov.uk"

    user = factories.user.create(email=email)
    grant = factories.grant.create()
    factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.MEMBER, grant=grant)

    login_user(user)
    with anonymous_client.session_transaction() as session:
        session["auth"] = AuthMethodEnum.SSO
    anonymous_client.user = user
    anonymous_client.grant = grant
    db_session.commit()

    yield anonymous_client


# TODO: combine (at least) the grant clients and allow the user+grant to come from another fixture so that we don't
#       need to attach them to the client; tests that want access to the configured user+grant could request the
#       fixture directly? Also maybe a pytest mark could be used to set the role provided for the authenticated grant
#       client rather than having two definitions.
@pytest.fixture()
def authenticated_grant_admin_client(
    anonymous_client: FundingServiceTestClient, factories: _Factories, db_session: Session, request: FixtureRequest
) -> Generator[FundingServiceTestClient, None, None]:
    email_mark = request.node.get_closest_marker("authenticate_as")
    email = email_mark.args[0] if email_mark else "test2@communities.gov.uk"

    user = factories.user.create(email=email)
    grant = factories.grant.create()
    factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.ADMIN, grant=grant)

    login_user(user)
    with anonymous_client.session_transaction() as session:
        session["auth"] = AuthMethodEnum.SSO
    anonymous_client.user = user
    anonymous_client.grant = grant
    db_session.commit()

    yield anonymous_client


@pytest.fixture()
def authenticated_platform_admin_client(
    anonymous_client: FundingServiceTestClient, factories: _Factories, db_session: Session, request: FixtureRequest
) -> Generator[FundingServiceTestClient, None, None]:
    email_mark = request.node.get_closest_marker("authenticate_as")
    email = email_mark.args[0] if email_mark else "test@communities.gov.uk"

    user = factories.user.create(email=email)
    factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.ADMIN)

    login_user(user)
    with anonymous_client.session_transaction() as session:
        session["auth"] = AuthMethodEnum.SSO
    anonymous_client.user = user
    db_session.commit()

    yield anonymous_client


def _setup_session_clean_tracking() -> None:
    # 1. When a transaction starts, assume session is clean
    @event.listens_for(Session, "after_begin")
    def after_begin(session: Session, transaction: SessionTransaction, connection: Connection) -> None:
        session.info["clean"] = True

    # 2. Before flush — catch dirty state even if flush hasn't happened yet
    @event.listens_for(Session, "before_flush")
    def before_flush(session: Session, flush_context: Any, instances: object | None) -> None:
        if session.new or session.dirty or session.deleted:
            session.info["clean"] = False

    # 3. Before commit — set false since session has changes and did not flush
    @event.listens_for(Session, "before_commit")
    def before_commit(session: Session) -> None:
        if session.new or session.dirty or session.deleted:
            session.info["clean"] = False

    # 4. After commit — reset clean flag
    @event.listens_for(Session, "after_commit")
    def after_commit(session: Session) -> None:
        session.info["clean"] = True

    # 5. After rollback — reset clean flag
    @event.listens_for(Session, "after_rollback")
    def after_rollback(session: Session) -> None:
        session.info["clean"] = True


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
