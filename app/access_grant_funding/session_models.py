import enum
from typing import Any, Self
from uuid import UUID

from flask import session
from pydantic import BaseModel, ValidationError

from app.constants import (
    SESSION_CREATE_ORGANISATION,
    SESSION_MATCHED_ORGANISATION,
    SESSION_SIGNING_UP_FOR_COLLECTION_ID,
)


class SignUpOrganisationType(enum.StrEnum):
    COMPANY = "COMPANY"
    CHARITY = "CHARITY"
    LOCAL_AUTHORITY = "LOCAL_AUTHORITY"
    OTHER = "OTHER"

    @property
    def label(self) -> str:
        """The radio label for this type, reused for the check-your-answers summary row so the two can't drift."""
        match self:
            case SignUpOrganisationType.COMPANY:
                return "Registered company"
            case SignUpOrganisationType.CHARITY:
                return "Charity"
            case SignUpOrganisationType.LOCAL_AUTHORITY:
                return "Local authority"
            case SignUpOrganisationType.OTHER:
                return "Other"


class SignUpSession(BaseModel):
    """State carried between the screens of a public sign up journey, in the signed session cookie."""

    collection_id: UUID

    def to_session_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def from_session(cls, *, collection_id: UUID, session_data: dict[str, Any]) -> Self | None:
        try:
            sign_up_session = cls.model_validate(session_data)
        except ValidationError:
            return None

        # pin to the current sign up, only one is valid at a time
        return sign_up_session if sign_up_session.collection_id == collection_id else None


class MatchedOrganisationSession(SignUpSession):
    """Only required when additional screens are needed during matching
    like asking for the users name
    """

    organisation_id: UUID


class CreateOrganisationSession(SignUpSession):
    organisation_type: SignUpOrganisationType | None = None
    name: str = ""
    external_id: str = ""
    # optional as only needed for users we don't have a name for on the model
    user_name: str | None = None
    # optional as only asked of users whose email domain isn't a shared provider
    allow_team_members: bool | None = None


def start_public_sign_up(collection_id: UUID) -> None:
    """Begin (or restart) a public sign up, discarding any in-progress organisation set up."""
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session.pop(SESSION_MATCHED_ORGANISATION, None)
    session[SESSION_SIGNING_UP_FOR_COLLECTION_ID] = collection_id


def clear_public_sign_up_session() -> UUID | None:
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session.pop(SESSION_MATCHED_ORGANISATION, None)
    return session.pop(SESSION_SIGNING_UP_FOR_COLLECTION_ID, None)
