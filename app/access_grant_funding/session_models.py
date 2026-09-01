from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.common.data.types import OrganisationType


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

    @property
    def organisation_type(self) -> OrganisationType | None:
        """The OrganisationType this maps to, or None where the mapping is not one-to-one.

        Local authorities span the nine types in ``_LOCAL_AUTHORITY_TYPES``; a future screen will resolve the
        specific one by having the user pick their authority, so there is nothing to map here yet.
        """
        match self:
            case SignUpOrganisationType.COMPANY:
                return OrganisationType.COMPANY
            case SignUpOrganisationType.CHARITY:
                return OrganisationType.CHARITY
            case SignUpOrganisationType.OTHER:
                return OrganisationType.OTHER
            case SignUpOrganisationType.LOCAL_AUTHORITY:
                return None


class CreateOrganisationSession(BaseModel):
    # required: an absent or stale session fails validation and bounces the user back to the start of the journey
    collection_id: UUID
    # `organisation_type` and `name` match the WTForms field names exactly so `Form(obj=session)` binds off the model
    organisation_type: SignUpOrganisationType | None = None
    name: str = ""
    custom_code: str = ""

    def to_session_dict(self) -> dict[str, Any]:
        # mode="json" so the UUID is serialised to a string rather than put into the signed cookie as a UUID object
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> CreateOrganisationSession:
        return cls.model_validate(session_data)
