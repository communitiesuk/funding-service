from datetime import datetime

import pytest

from app.common.data.types import (
    SubmissionEventType,
    SubmissionStatusEnum,
)
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.submission_events import SubmissionEventHelper


class TestSubmissionValidationStatus:
    """Tests for submission status calculation with validation events."""

    def test_submitted_with_validation_required_stays_submitted(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        question = factories.question.build(form__collection=collection)
        user = factories.user.build()
        submission = factories.submission.build(
            collection=collection,
            data={str(question.id): "test answer"},
        )
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=question.form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
        ]
        helper = SubmissionHelper(submission)
        assert helper.status == SubmissionStatusEnum.SUBMITTED

    def test_validated_status(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        question = factories.question.build(form__collection=collection)
        user = factories.user.build()
        submission = factories.submission.build(
            collection=collection,
            data={str(question.id): "test answer"},
        )
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=question.form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_VALIDATED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_VALIDATED),
                created_at_utc=datetime(2026, 1, 3, 0, 0, 0),
            ),
        ]
        helper = SubmissionHelper(submission)
        assert helper.status == SubmissionStatusEnum.VALIDATED
        assert helper.is_validated is True
        assert helper.is_locked_state is True

    def test_declined_status(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        question = factories.question.build(form__collection=collection)
        user = factories.user.build()
        submission = factories.submission.build(
            collection=collection,
            data={str(question.id): "test answer"},
        )
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=question.form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_VALIDATION_DECLINED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(
                    SubmissionEventType.SUBMISSION_VALIDATION_DECLINED, declined_reason="Invalid data"
                ),
                created_at_utc=datetime(2026, 1, 3, 0, 0, 0),
            ),
        ]
        helper = SubmissionHelper(submission)
        assert helper.status == SubmissionStatusEnum.DECLINED
        assert helper.is_declined is True
        assert helper.is_locked_state is True

    def test_changes_requested_returns_to_in_progress(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        question = factories.question.build(form__collection=collection)
        user = factories.user.build()
        submission = factories.submission.build(
            collection=collection,
            data={str(question.id): "test answer"},
        )
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=question.form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED_BY_VALIDATOR,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(
                    SubmissionEventType.SUBMISSION_CHANGES_REQUESTED_BY_VALIDATOR, declined_reason="Fix numbers"
                ),
                created_at_utc=datetime(2026, 1, 3, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_VALIDATOR,
                related_entity_id=question.form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_VALIDATOR),
                created_at_utc=datetime(2026, 1, 3, 0, 0, 1),
            ),
        ]
        helper = SubmissionHelper(submission)
        assert helper.status == SubmissionStatusEnum.IN_PROGRESS
        assert helper.is_locked_state is False

    def test_validate_raises_when_not_submitted(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        factories.question.build(form__collection=collection)
        submission = factories.submission.build(collection=collection)
        helper = SubmissionHelper(submission)

        with pytest.raises(ValueError, match="not in submitted status"):
            helper.validate_submission(factories.user.build())

    def test_validate_raises_when_validation_not_required(self, factories):
        collection = factories.collection.build(requires_validation=False, requires_certification=False)
        question = factories.question.build(form__collection=collection)
        user = factories.user.build()
        submission = factories.submission.build(
            collection=collection,
            data={str(question.id): "test answer"},
        )
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=question.form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
        ]
        helper = SubmissionHelper(submission)

        with pytest.raises(ValueError, match="does not require validation"):
            helper.validate_submission(factories.user.build())

    def test_request_changes_raises_when_not_submitted(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        factories.question.build(form__collection=collection)
        submission = factories.submission.build(collection=collection)
        helper = SubmissionHelper(submission)

        with pytest.raises(ValueError, match="not in submitted status"):
            helper.request_changes_on_submission(factories.user.build(), reason="Bad data")

    def test_decline_raises_when_not_submitted(self, factories):
        collection = factories.collection.build(requires_validation=True, requires_certification=False)
        factories.question.build(form__collection=collection)
        submission = factories.submission.build(collection=collection)
        helper = SubmissionHelper(submission)

        with pytest.raises(ValueError, match="not in submitted status"):
            helper.decline_validation(factories.user.build(), reason="Bad")


class TestSubmissionValidationEventState:
    """Tests for the event state reduction with validation events."""

    def test_validated_state(self, factories):
        user = factories.user.build()
        submission = factories.submission.build()
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_VALIDATED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_VALIDATED),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
        ]
        events = SubmissionEventHelper(submission)
        state = events.submission_state
        assert state.is_submitted is True
        assert state.is_validated is True
        assert state.is_validation_declined is False
        assert state.validated_by == user
        assert state.validated_at_utc == datetime(2026, 1, 2, 0, 0, 0)

    def test_declined_state(self, factories):
        user = factories.user.build()
        submission = factories.submission.build()
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_VALIDATION_DECLINED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(
                    SubmissionEventType.SUBMISSION_VALIDATION_DECLINED, declined_reason="Invalid data"
                ),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
        ]
        events = SubmissionEventHelper(submission)
        state = events.submission_state
        assert state.is_submitted is True
        assert state.is_validation_declined is True
        assert state.is_validated is False
        assert state.declined_reason == "Invalid data"
        assert state.validation_declined_by == user
        assert state.validation_declined_at_utc == datetime(2026, 1, 2, 0, 0, 0)

    def test_changes_requested_resets_submitted(self, factories):
        user = factories.user.build()
        submission = factories.submission.build()
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED_BY_VALIDATOR,
                related_entity_id=submission.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(
                    SubmissionEventType.SUBMISSION_CHANGES_REQUESTED_BY_VALIDATOR, declined_reason="Fix numbers"
                ),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
        ]
        events = SubmissionEventHelper(submission)
        state = events.submission_state
        assert state.is_submitted is False
        assert state.is_validated is False
        assert state.is_validation_declined is False
        assert state.declined_reason == "Fix numbers"
        assert state.changes_requested_by == user
        assert state.changes_requested_at_utc == datetime(2026, 1, 2, 0, 0, 0)

    def test_form_reset_by_validator(self, factories):
        form = factories.form.build()
        user = factories.user.build()
        submission = factories.submission.build(collection=form.collection)
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2026, 1, 1, 0, 0, 0),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_VALIDATOR,
                related_entity_id=form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_VALIDATOR),
                created_at_utc=datetime(2026, 1, 2, 0, 0, 0),
            ),
        ]
        events = SubmissionEventHelper(submission)
        assert events.form_state(form.id).is_completed is False
