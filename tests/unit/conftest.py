import os
from datetime import date, datetime
from typing import Generator
from unittest.mock import patch

import pytest
from _pytest.fixtures import FixtureRequest
from flask import Flask
from flask_sqlalchemy_lite import SQLAlchemy

from app import create_app
from app.common.data.models import Submission
from app.common.data.types import SubmissionEventType, SubmissionModeEnum
from tests.conftest import _Factories, _precompile_templates
from tests.utils import build_db_config


@pytest.fixture(scope="session", autouse=True)
def _unit_test_timeout(request: FixtureRequest) -> None:
    """Fail tests under `tests/unit` if they take more than 1ms, to encourage us to maintain tests that are
    very fast here.

    These tests should not need to do anything over the network and are likely to make use of mocking to keep the
    amount of code under test fairly tight, so this should not be hard to meet.
    """
    request.node.add_marker(pytest.mark.fail_slow("10ms"))


@pytest.fixture(scope="session")
def app() -> Generator[Flask, None, None]:
    with patch.dict(os.environ, build_db_config(None)):
        app = create_app()

    app.config.update({"TESTING": True})
    _precompile_templates(app)
    yield app


@pytest.fixture(scope="function", autouse=True)
def db_session(app: Flask) -> Generator[None, None, None]:
    # No-op fixture that blocks access to the DB by default. Fixtures in the `integration` sub-directory will properly
    # set up the database connection/session with transactional isolation between tests.
    # This blank fixture helps us still provide the ability to use FactoryBoy to build ephemeral instances of our DB
    # models for unit testing.
    #
    # NOTE: this fixture is automatically used by all unit tests, and provides both an app context and a test request
    # context. So you will not need to manually create these within your unit tests.

    with app.app_context():
        original_session_property = SQLAlchemy.session

        def session_error(self: SQLAlchemy) -> None:
            raise RuntimeError("No access to DB session available outside of integration tests")

        SQLAlchemy.session = property(session_error)  # type: ignore[method-assign, assignment]

        try:
            yield
        finally:
            SQLAlchemy.session = original_session_property  # type: ignore[method-assign]


@pytest.fixture(scope="function")
def submission_awaiting_sign_off(factories: _Factories) -> Generator[Submission, None, None]:
    grant_recipient = factories.grant_recipient.build(
        grant__name="Test grant",
    )

    question = factories.question.build(
        form__collection__grant=grant_recipient.grant,
        form__collection__name="Test collection",
        form__collection__submission_period_end_date=date(
            2025,
            12,
            3,
        ),
    )
    submission = factories.submission.build(
        grant_recipient=grant_recipient,
        collection=question.form.collection,
        mode=SubmissionModeEnum.LIVE,
        data={str(question.id): "Question answer"},
    )
    submitted_by = factories.user.build(name="Submitter User", email="submitter@test.com")

    form = submission.collection.forms[0]

    factories.submission_event.build(
        submission=submission,
        related_entity_id=form.id,
        event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        created_by=submitted_by,
        created_at_utc=datetime(2025, 11, 25, 11, 0, 0),
    )
    factories.submission_event.build(
        submission=submission,
        event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
        created_by=submitted_by,
        created_at_utc=datetime(2025, 11, 26, 13, 30, 0),
    )

    yield submission
