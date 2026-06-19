from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.common.data.types import SubmissionEventType

if TYPE_CHECKING:
    from app.common.data.models import Submission, SubmissionEvent


@dataclass
class TimelineEvent:
    type: SubmissionEventType
    datetime: datetime
    source: SubmissionEvent


def from_submission_event(event: SubmissionEvent) -> TimelineEvent:
    return TimelineEvent(
        type=event.event_type,
        datetime=event.created_at_utc,
        source=event,
    )


def build_timeline_events(submission: Submission) -> list[TimelineEvent]:
    submission_events = [from_submission_event(event) for event in submission.events]

    return sorted(submission_events, key=lambda e: e.datetime, reverse=True)
