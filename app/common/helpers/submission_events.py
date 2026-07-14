from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypedDict, Unpack, overload
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.data.models_user import User
from app.common.data.types import SubmissionEventType

if TYPE_CHECKING:
    from app.common.data.models import Submission, SubmissionEvent


class SubmissionEventBase(BaseModel):
    """Base class for all submission event dataclasses."""

    event_type: ClassVar[SubmissionEventType]


class FormCompletedEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.FORM_RUNNER_FORM_COMPLETED
    is_completed: bool = True


class FormResetToInProgressEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
    is_completed: bool = False


class FormResetByCertifierEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_CERTIFIER
    is_completed: bool = False


class SubmissionSentForCertificationEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
    is_awaiting_sign_off: bool = True
    is_approved: bool = False


class SubmissionDeclinedByCertifierEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER
    is_awaiting_sign_off: bool = False
    is_approved: bool = False
    declined_reason: str | None = Field(default=None, json_schema_extra={"stored": True})


class SubmissionReopenedEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.SUBMISSION_REOPENED
    is_awaiting_sign_off: bool = False
    is_approved: bool = False
    is_submitted: bool = False
    reopened_reason: str = Field(json_schema_extra={"stored": True})
    submission_data: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"stored": True})


class SubmissionChangesRequestedEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.SUBMISSION_CHANGES_REQUESTED
    is_awaiting_sign_off: bool = False
    is_approved: bool = False
    is_submitted: bool = False
    changes_requested_reason: str = Field(json_schema_extra={"stored": True})
    submission_data: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"stored": True})
    section_ids: list[UUID] = Field(default_factory=list, json_schema_extra={"stored": True})
    is_changes_requested: bool = True


class DeclinedByCertifierKwargs(TypedDict, total=False):
    """
    TypedDict to help ty correctly enforce kwargs that should be passed when creating Events that have
    attributes which can vary for each instance.
    """

    declined_reason: str | None


class ReopenedKwargs(TypedDict, total=False):
    reopened_reason: str | None
    submission_data: dict[str, Any] | None


class ChangesRequestedKwargs(TypedDict, total=False):
    changes_requested_reason: str | None
    submission_data: dict[str, Any] | None
    section_ids: list[UUID]


class SubmissionApprovedByCertifierEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER
    is_awaiting_sign_off: bool = False
    is_approved: bool = True


class SubmissionSubmittedEvent(SubmissionEventBase):
    event_type: ClassVar[SubmissionEventType] = SubmissionEventType.SUBMISSION_SUBMITTED
    is_submitted: bool = True
    is_changes_requested: bool = False


# State - represents a snapshot of the current state of the target entity for those events
# Combines metadata about who has been doing the events and the event properties themselves
class SentForCertificationMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    sent_for_certification_by: User | None = None
    sent_for_certification_at_utc: datetime | None = None


class CertifiedMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    certified_by: User | None = None
    certified_at_utc: datetime | None = None


class CertificationDeclinedMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    declined_by: User | None = None
    declined_at_utc: datetime | None = None


class SubmittedMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    submitted_by: User | None = None
    submitted_at_utc: datetime | None = None


class ReopenedMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    reopened_by: User | None = None
    reopened_at_utc: datetime | None = None


class ChangesRequestedMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    changes_requested_by: User | None = None
    changes_requested_at_utc: datetime | None = None


class SubmissionState(
    SentForCertificationMetadata,
    SubmittedMetadata,
    CertifiedMetadata,
    CertificationDeclinedMetadata,
    ReopenedMetadata,
    ChangesRequestedMetadata,
):
    is_awaiting_sign_off: bool | None = None
    is_submitted: bool = False
    is_approved: bool | None = None
    declined_reason: str | None = None
    reopened_reason: str | None = None
    changes_requested_reason: str | None = None
    submission_data: dict[str, Any] | None = None
    section_ids: list[UUID] = Field(default_factory=list)
    is_changes_requested: bool = False


class FormState(BaseModel):
    is_completed: bool = False


def _shallow_dict(model: BaseModel) -> dict[str, Any]:
    """Return model field values without deep serialization (preserves ORM instances etc)."""
    return {name: getattr(model, name) for name in type(model).model_fields}


_SUBMISSION_EVENT_REGISTRY = {event.event_type: event for event in SubmissionEventBase.__subclasses__()}
if len(_SUBMISSION_EVENT_REGISTRY) != len(SubmissionEventType):
    raise RuntimeError("Not all SubmissionEventType values have been registered")


def _get_event_class(event_type: SubmissionEventType) -> type[SubmissionEventBase]:
    return _SUBMISSION_EVENT_REGISTRY[event_type]


def _get_stored_field_names(event_class: type[SubmissionEventBase]) -> set[str]:
    return {
        name
        for name, field_info in event_class.model_fields.items()
        if field_info.json_schema_extra and field_info.json_schema_extra.get("stored", False)
    }


def _get_static_data(event_class: type[SubmissionEventBase]) -> dict[str, Any]:
    stored = _get_stored_field_names(event_class)
    result: dict[str, Any] = {}
    for name, field_info in event_class.model_fields.items():
        if name not in stored:
            if field_info.default is not None:
                result[name] = field_info.default
            elif field_info.default_factory is not None:
                result[name] = field_info.default_factory()
    return result


class SubmissionEventHelper:
    def __init__(self, submission: Submission):
        self.submission = submission

    @property
    def events(self) -> list[SubmissionEvent]:
        return sorted(self.submission.events, key=lambda x: x.created_at_utc, reverse=False)

    def form_state(self, form_id: UUID) -> FormState:
        return FormState(**self._reduce([e for e in self.events if e.related_entity_id == form_id]))

    @property
    def submission_state(self) -> SubmissionState:
        return SubmissionState(**self._reduce([e for e in self.events if e.related_entity_id == self.submission.id]))

    def _reduce(self, events: list[SubmissionEvent]) -> dict[str, Any]:
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
            event_class = _get_event_class(event.event_type)
            state = state | _get_static_data(event_class) | event.data | self._extract_metadata(event)

        return state

    def _extract_metadata(self, event: SubmissionEvent) -> dict[str, Any]:
        """
        Pull out typed objects from the SubmissionEvent table that are associated with a given event.

        This metadata will be available to the snapshot state and can include any referenced properties.
        """
        match event.event_type:
            case SubmissionEventType.SUBMISSION_SUBMITTED:
                return _shallow_dict(
                    SubmittedMetadata(
                        submitted_by=event.created_by,
                        submitted_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION:
                return _shallow_dict(
                    SentForCertificationMetadata(
                        sent_for_certification_by=event.created_by,
                        sent_for_certification_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER:
                return _shallow_dict(
                    CertifiedMetadata(
                        certified_by=event.created_by,
                        certified_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER:
                return _shallow_dict(
                    CertificationDeclinedMetadata(
                        declined_by=event.created_by,
                        declined_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_REOPENED:
                return _shallow_dict(
                    ReopenedMetadata(
                        reopened_by=event.created_by,
                        reopened_at_utc=event.created_at_utc,
                    )
                )
            case SubmissionEventType.SUBMISSION_CHANGES_REQUESTED:
                return _shallow_dict(
                    ChangesRequestedMetadata(
                        changes_requested_by=event.created_by,
                        changes_requested_at_utc=event.created_at_utc,
                    )
                )
            case _:
                return {}

    @overload
    @staticmethod
    def event_from(
        event_type: Literal[SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER],
        **kwargs: Unpack[DeclinedByCertifierKwargs],
    ) -> dict[str, Any]: ...

    @overload
    @staticmethod
    def event_from(
        event_type: Literal[SubmissionEventType.SUBMISSION_REOPENED],
        **kwargs: Unpack[ReopenedKwargs],
    ) -> dict[str, Any]: ...

    @overload
    @staticmethod
    def event_from(
        event_type: Literal[SubmissionEventType.SUBMISSION_CHANGES_REQUESTED],
        **kwargs: Unpack[ChangesRequestedKwargs],
    ) -> dict[str, Any]: ...

    @overload
    @staticmethod
    def event_from(
        event_type: SubmissionEventType,
    ) -> dict[str, Any]: ...

    @staticmethod
    def event_from(event_type: SubmissionEventType, **kwargs: Any) -> dict[str, Any]:
        event_class = _get_event_class(event_type)
        stored_field_names = _get_stored_field_names(event_class)
        stored_kwargs = {k: v for k, v in kwargs.items() if k in stored_field_names}
        if not stored_kwargs:
            return {}
        event = event_class(**{**stored_kwargs, **{k: v for k, v in kwargs.items() if k not in stored_field_names}})
        return event.model_dump(mode="json", include=stored_field_names)
