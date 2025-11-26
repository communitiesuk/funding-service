from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from app.common.data.types import SubmissionEventType

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from app.common.data.models import Submission, SubmissionEvent
    from app.common.data.models_user import User


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


@dataclass
class SentForCertificationMetadata:
    sent_for_certification_by: "User | None" = None
    sent_for_certification_at_utc: "datetime | None" = None


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
        return FormState(**self._reduce([e for e in self.events if e.target_key == form_id]))

    @property
    def submission_state(self) -> SubmissionState:
        return SubmissionState(**self._reduce([e for e in self.events if e.target_key == self.submission.id]))

    def _reduce(self, events: list["SubmissionEvent"]) -> dict[str, Any]:
        state: dict[str, Any] = {}
        for event in events:
            state = state | event.data | self._extract_metadata(event)

        return state

    def _extract_metadata(self, event: "SubmissionEvent") -> dict[str, Any]:
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
    return {field.name: getattr(obj, field.name) for field in fields(obj)}
