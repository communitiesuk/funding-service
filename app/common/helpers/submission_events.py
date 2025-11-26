from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from app.common.data.types import SubmissionEventType

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from app.common.data.models import Submission, SubmissionEvent
    from app.common.data.models_user import User


# Mixins - schema protocol used to guarantee that the properties we're tracking using events
# and our final state line up
@dataclass
class CompletedMixin(Protocol):
    is_completed: bool


@dataclass
class SignOffMixin(Protocol):
    is_awaiting_sign_off: bool
    is_approved: bool


@dataclass
class SubmittedMixin(Protocol):
    is_submitted: bool


# Events - things that can happen in the service, we calculate the final state
# by taking all the latest event properties allowing workflows to go forward and backwards
# Event names are past tense
@dataclass
class DeclinedMixin(Protocol):
    declined_reason: str | None


@dataclass
class FormCompletedEvent(CompletedMixin):
    is_completed: bool = True


@dataclass
class FormResetToInProgressEvent(CompletedMixin):
    is_completed: bool = False


@dataclass
class FormResetByCertifierEvent(CompletedMixin):
    is_completed: bool = False


@dataclass
class SubmissionSentForCertificationEvent(SignOffMixin):
    is_awaiting_sign_off: bool = True
    is_approved: bool = False


@dataclass
class SubmissionDeclinedByCertifierEvent(SignOffMixin, DeclinedMixin):
    is_awaiting_sign_off: bool = False
    is_approved: bool = False
    declined_reason: str | None = None


@dataclass
class SubmissionApprovedByCertifierEvent(SignOffMixin):
    is_awaiting_sign_off: bool = False
    is_approved: bool = True


@dataclass
class SubmissionSubmittedEvent(SubmittedMixin, SignOffMixin):
    is_submitted: bool = True
    is_awaiting_sign_off: bool = False
    is_approved: bool = False


# State - represents a snapshot of the current state of the target entity for those events
# Combines metadata about who has been doing the events and the event properties themselves
@dataclass
class SentForCertificationMetadata:
    sent_for_certification_by: "User | None" = None
    sent_for_certification_at_utc: datetime | None = None


@dataclass
class CertifiedMetadata:
    certified_by: "User | None" = None
    certified_at_utc: "datetime | None" = None


@dataclass
class SubmittedMetadata:
    submitted_by: "User | None" = None
    submitted_at_utc: datetime | None = None


@dataclass
class SubmissionState(
    SentForCertificationMetadata, SubmittedMetadata, CertifiedMetadata, SignOffMixin, SubmittedMixin, DeclinedMixin
):
    is_awaiting_sign_off: bool = False
    is_submitted: bool = False
    is_approved: bool = False
    declined_reason: str | None = None


@dataclass
class FormState(CompletedMixin):
    is_completed: bool = False


class SubmissionEventHelper:
    def __init__(self, submission: "Submission"):
        self.submission = submission

    @property
    def events(self) -> list["SubmissionEvent"]:
        return sorted(self.submission.events, key=lambda x: x.created_at_utc, reverse=False)

    def form_state(self, form_id: UUID) -> FormState:
        return FormState(**self._reduce([e for e in self.events if e.related_entity_id == form_id]))

    @property
    def submission_state(self) -> SubmissionState:
        return SubmissionState(**self._reduce([e for e in self.events if e.related_entity_id == self.submission.id]))

    def _reduce(self, events: list["SubmissionEvent"]) -> dict[str, Any]:
        """
        An internal method to combine the full list of submission events into one snapshot
        representation, we take all of the data properties from each event in time order where
        newer properties will override previous.

        "Metadata" allows us to pull current values taking advantage of the relational database
        (rather than storing copies of all of the data on each event and giving foreign key guarantees)
        the database model (SubmissionEvent) will always track which user has done the action and
        when it was done - for some events we rely on this information throughout the app so these
        are mapped during this combination.

        This allows for scenarios like:
        - SUBMISSION_SENT_FOR_CERTIFICATION { "is_awaiting_sign_off": True }

        State is now { "is_awaiting_sign_off": True }

        - SUBMISSION_SUBMITTED { "is_awaiting_sign_off": False, "is_submitted": True }

        State is now { "is_awaiting_sign_off": False, "is_submitted": True }

        Because SUBMISSION_SUBMITTED was recorded after SUBMISSION_SENT_FOR_CERTIFICATION the overlapping
        property "is_awaiting_sign_off" will take its value.
        """
        state: dict[str, Any] = {}
        for event in events:
            state = state | event.data | self._extract_metadata(event)

        return state

    def _extract_metadata(self, event: "SubmissionEvent") -> dict[str, Any]:
        """
        Pull out typed objects from the SubmissionEvent table that are associated with a given event.

        This metadata will be available to the snapshot state and can include any referenced properties.
        """
        match event.event_type:
            case SubmissionEventType.SUBMISSION_SUBMITTED:
                return shallow_asdict(
                    SubmittedMetadata(
                        submitted_by=event.created_by,
                        submitted_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION:
                return shallow_asdict(
                    SentForCertificationMetadata(
                        sent_for_certification_by=event.created_by,
                        sent_for_certification_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER:
                return shallow_asdict(
                    CertifiedMetadata(
                        certified_by=event.created_by,
                        certified_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER:
                return shallow_asdict(
                    CertifiedMetadata(
                        certified_by=event.created_by,
                        certified_at_utc=event.created_at_utc,
                    )
                )
            case _:
                return {}

    @staticmethod
    def event_from(event_type: SubmissionEventType, **kwargs: Any) -> dict[str, Any]:
        match event_type:
            case SubmissionEventType.FORM_RUNNER_FORM_COMPLETED:
                return asdict(FormCompletedEvent())
            case SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS:
                return asdict(FormResetToInProgressEvent())
            case SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_CERTIFIER:
                return asdict(FormResetByCertifierEvent())
            case SubmissionEventType.SUBMISSION_SUBMITTED:
                return asdict(SubmissionSubmittedEvent())
            case SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION:
                return asdict(SubmissionSentForCertificationEvent())
            case SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER:
                return asdict(SubmissionDeclinedByCertifierEvent(declined_reason=kwargs.get("declined_reason", None)))
            case SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER:
                return asdict(SubmissionApprovedByCertifierEvent())
            case _:
                raise NotImplementedError(f"No event class defined for event type {event_type}")


def shallow_asdict(obj: "DataclassInstance") -> dict[str, Any]:
    """
    Avoid duplicating properties when using the default dataclass `asdict` method, when collecting
    metadata to build state we always want to reference ORM models and not recreate them.

    See https://docs.python.org/3/library/dataclasses.html#dataclasses.asdict
    """
    return {field.name: getattr(obj, field.name) for field in fields(obj)}
