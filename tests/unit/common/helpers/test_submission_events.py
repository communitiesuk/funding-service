import uuid
from datetime import datetime

from app.common.data.types import SubmissionEventType
from app.common.helpers.submission_events import SubmissionEventHelper


class TestSubmissionEventHelper:
    class TestFormState:
        def test_empty(self, factories):
            submission = factories.submission.build()
            events = SubmissionEventHelper(submission)
            form_state = events.form_state(uuid.uuid4())
            assert form_state.is_completed is False

        def test_reduces(self, factories):
            form = factories.form.build()
            user = factories.user.build()
            submission = factories.submission.build(collection=form.collection)
            submission.events = [
                factories.submission_event.build(
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                    related_entity_id=form.id,
                    created_by=user,
                    data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                ),
            ]
            events = SubmissionEventHelper(submission)
            assert events.form_state(form.id).is_completed is True

        def test_reduces_in_order(self, factories):
            form = factories.form.build()
            user = factories.user.build()
            submission = factories.submission.build(collection=form.collection)
            submission.events = [
                factories.submission_event.build(
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                    related_entity_id=form.id,
                    created_by=user,
                    data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                    created_at_utc=datetime(2025, 11, 25, 0, 0, 0),
                ),
                factories.submission_event.build(
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS,
                    related_entity_id=form.id,
                    created_by=user,
                    data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS),
                    created_at_utc=datetime(2025, 11, 26, 0, 0, 0),
                ),
            ]
            events = SubmissionEventHelper(submission)
            assert events.form_state(form.id).is_completed is False

            factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                related_entity_id=form.id,
                created_by=user,
                data=SubmissionEventHelper.event_from(SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
                created_at_utc=datetime(2025, 11, 27, 0, 0, 0),
            )
            assert events.form_state(form.id).is_completed is True

    class TestSubmissionState:
        def test_empty(self, factories):
            submission = factories.submission.build()
            events = SubmissionEventHelper(submission)
            submission_state = events.submission_state
            assert submission_state.is_submitted is False
            assert submission_state.is_awaiting_sign_off is False
            assert submission_state.submitted_by is None
            assert submission_state.submitted_at_utc is None
            assert submission_state.sent_for_certification_by is None
            assert submission_state.sent_for_certification_at_utc is None

        def test_reduces(self, factories):
            form = factories.form.build()
            user = factories.user.build()
            submission = factories.submission.build(
                collection=form.collection,
            )
            submission.events = [
                factories.submission_event.build(
                    event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                    related_entity_id=submission.id,
                    created_by=user,
                    data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION),
                    created_at_utc=datetime(2025, 11, 25, 0, 0, 0),
                )
            ]
            events = SubmissionEventHelper(submission)
            submission_state = events.submission_state
            assert submission_state.is_awaiting_sign_off is True
            assert submission_state.sent_for_certification_by == user
            assert submission_state.sent_for_certification_at_utc == datetime(2025, 11, 25, 0, 0, 0)
            assert submission_state.is_submitted is False
            assert submission_state.submitted_by is None

        def test_reduces_in_order(self, factories):
            form = factories.form.build()
            user = factories.user.build()
            submission = factories.submission.build(
                collection=form.collection,
            )
            submission.events = [
                factories.submission_event.build(
                    event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                    related_entity_id=submission.id,
                    created_by=user,
                    data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION),
                    created_at_utc=datetime(2025, 11, 24, 0, 0, 0),
                ),
                factories.submission_event.build(
                    event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                    related_entity_id=submission.id,
                    created_by=user,
                    data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
                    created_at_utc=datetime(2025, 11, 25, 0, 0, 0),
                ),
            ]
            events = SubmissionEventHelper(submission)
            assert events.submission_state.is_submitted is True
            assert events.submission_state.is_awaiting_sign_off is False
            assert events.submission_state.submitted_by == user
            assert events.submission_state.submitted_at_utc == datetime(2025, 11, 25, 0, 0, 0)
            assert events.submission_state.sent_for_certification_by == user
            assert events.submission_state.sent_for_certification_at_utc == datetime(2025, 11, 24, 0, 0, 0)
