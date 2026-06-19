from datetime import datetime

from app.common.data.types import SubmissionEventType
from app.common.helpers.timeline import build_timeline_events, from_submission_event


class TestFromSubmissionEvent:
    def test_from_submission_event(self, factories):
        dt = datetime(2025, 6, 1, 12, 0, 0)

        event = factories.submission_event.build(
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
            created_at_utc=dt,
        )

        timeline_event = from_submission_event(event)

        assert timeline_event.type == SubmissionEventType.SUBMISSION_SUBMITTED
        assert timeline_event.datetime == dt
        assert timeline_event.source is event


class TestBuildTimelineEvents:
    def test_empty(self, factories):
        submission = factories.submission.build()
        submission.events = []

        assert build_timeline_events(submission) == []

    def test_includes_all_event_types(self, factories):
        submission = factories.submission.build()
        submission.events = [
            factories.submission_event.build(event_type=SubmissionEventType.SUBMISSION_SUBMITTED),
            factories.submission_event.build(event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED),
            factories.submission_event.build(event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER),
        ]

        result = build_timeline_events(submission)

        assert len(result) == 3

    def test_sorted_most_recent_first(self, factories):
        submission = factories.submission.build()
        submission.events = [
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                created_at_utc=datetime(2025, 1, 1),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                created_at_utc=datetime(2025, 3, 1),
            ),
            factories.submission_event.build(
                event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
                created_at_utc=datetime(2025, 2, 1),
            ),
        ]

        result = build_timeline_events(submission)

        assert [e.datetime for e in result] == [
            datetime(2025, 3, 1),
            datetime(2025, 2, 1),
            datetime(2025, 1, 1),
        ]
