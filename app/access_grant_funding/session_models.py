import enum
from typing import Any, Self
from uuid import UUID

from flask import session
from pydantic import BaseModel, Field, ValidationError, ValidationInfo, model_validator

from app.common.data.models_user import User
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
    def from_session(
        cls, *, collection_id: UUID, session_data: dict[str, Any], user: User | None = None
    ) -> Self | None:
        """Reads the session, returning None if it doesn't hold everything `cls` requires.

        Subclasses tighten the fields to say which answers a screen can't be shown without; a couple of
        those answers are only needed for some users, so `user` is made available to their validators.
        """
        try:
            sign_up_session = cls.model_validate(session_data, context={"user": user})
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
    """A create organisation journey in progress, with nothing answered yet."""

    organisation_type: SignUpOrganisationType | None = None
    name: str | None = None
    external_id: str | None = None
    # optional as only needed for users we don't have a name for on the model
    user_name: str | None = None
    # optional as only asked of users whose email domain isn't a shared provider
    allow_team_members: bool | None = None


class NamedCreateOrganisationSession(CreateOrganisationSession):
    organisation_type: SignUpOrganisationType
    name: str = Field(min_length=1)
    external_id: str = Field(min_length=1)


class CompleteCreateOrganisationSession(NamedCreateOrganisationSession):
    @model_validator(mode="after")
    def check_properties_that_can_be_skipped(self, info: ValidationInfo) -> Self:
        # TODO: when the session specifies if the email can be shared and if the user has a name
        #       when it is originally initialised we can remove passing the user info into the session
        user: User | None = (info.context or {}).get("user")
        if user is None:
            raise TypeError(f"{type(self).__name__} can only be validated with the user the session belongs to")

        if not self.user_name and not user.name:
            raise ValueError("we hold no name for this user and they haven't given one")
        if self.allow_team_members is None and user.can_share_email_domain:
            raise ValueError("this user was asked to allow team members but hasn't answered")

        return self


def start_public_sign_up(collection_id: UUID) -> None:
    """Begin (or restart) a public sign up, discarding any in-progress organisation set up."""
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session.pop(SESSION_MATCHED_ORGANISATION, None)
    session[SESSION_SIGNING_UP_FOR_COLLECTION_ID] = collection_id


def clear_public_sign_up_session() -> UUID | None:
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session.pop(SESSION_MATCHED_ORGANISATION, None)
    return session.pop(SESSION_SIGNING_UP_FOR_COLLECTION_ID, None)
