import enum
from typing import Any, Self
from uuid import UUID

from flask import session
from pydantic import BaseModel, Field, ValidationError, model_validator

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
    def from_session(cls, *, collection_id: UUID, session_data: dict[str, Any]) -> Self | None:
        """Reads the session, returning None if it doesn't hold everything `cls` requires.

        Subclasses tighten the fields to say which answers a screen can't be shown without.
        """
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
    """A create organisation journey in progress, with nothing answered yet."""

    # which of the optional steps this user is asked is settled when the journey starts, so that
    # the screens along it don't each have to work it out from the user again
    needs_user_name: bool
    can_share_email_domain: bool

    organisation_type: SignUpOrganisationType | None = None
    name: str | None = None
    # the generated custom code for organisations we identify ourselves; unset for registered companies
    external_id: str | None = None
    # set when the organisation was selected from the Companies House register; unset otherwise
    companies_house_number: str | None = None
    # optional as only needed for users we don't have a name for on the model
    user_name: str | None = None
    # optional as only asked of users whose email domain isn't a shared provider
    allow_team_members: bool | None = None

    @classmethod
    def start(cls, *, collection_id: UUID, user: User) -> Self:
        return cls(
            collection_id=collection_id,
            needs_user_name=not user.name,
            can_share_email_domain=user.can_share_email_domain,
        )

    @property
    def is_registered_company(self) -> bool:
        return self.organisation_type == SignUpOrganisationType.COMPANY and bool(self.companies_house_number)

    @property
    def typed_id(self) -> str:
        """The identifier that will be stored against the organisation's type when it is created."""
        return (self.companies_house_number if self.is_registered_company else self.external_id) or ""


class NamedCreateOrganisationSession(CreateOrganisationSession):
    organisation_type: SignUpOrganisationType
    name: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_organisation_is_identified(self) -> Self:
        if not self.typed_id:
            raise ValueError("Organisation identifier required")

        return self


class CompleteCreateOrganisationSession(NamedCreateOrganisationSession):
    @model_validator(mode="after")
    def check_properties_that_can_be_skipped(self) -> Self:
        if self.needs_user_name and not self.user_name:
            raise ValueError("Users full name required")
        if self.can_share_email_domain and self.allow_team_members is None:
            raise ValueError("Must specify if team members allowed through email domain")

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
