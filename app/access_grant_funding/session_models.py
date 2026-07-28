import enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.common.data.types import OrganisationType


class SignUpOrganisationType(enum.StrEnum):
    COMPANY = "company"
    CHARITY = "charity"
    LOCAL_AUTHORITY = "local authority"
    OTHER = "other"

    @property
    def organisation_type(self) -> OrganisationType | None:
        """The OrganisationType we'd store, or None for types we can't self-register."""
        match self:
            case SignUpOrganisationType.COMPANY:
                return OrganisationType.COMPANY
            case SignUpOrganisationType.CHARITY:
                return OrganisationType.CHARITY
            case SignUpOrganisationType.OTHER:
                return OrganisationType.OTHER
            case SignUpOrganisationType.LOCAL_AUTHORITY:
                return None


class PublicSignUpSession(BaseModel):
    collection_id: UUID
    organisation_type: SignUpOrganisationType | None = None
    has_reference_number: Literal["yes", "no"] | None = None
    reference_number: str = ""
    organisation_name: str = ""  # resolved from the mock registry, or typed directly for OTHER

    def to_session_dict(self) -> dict[str, Any]:
        """Convert to dict for session storage"""
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> PublicSignUpSession:
        """Create from session dict with validation"""
        return cls.model_validate(session_data)
