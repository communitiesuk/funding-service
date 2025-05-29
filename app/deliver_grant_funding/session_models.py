from typing import Any, Literal

from pydantic import BaseModel


class GrantSetupGGIS(BaseModel):
    has_ggis: Literal["yes", "no"]
    ggis_number: str | None = None


class GrantSetupName(BaseModel):
    name: str


class GrantSetupDescription(BaseModel):
    description: str


class GrantSetupContact(BaseModel):
    primary_contact_name: str
    primary_contact_email: str


class GrantSetupSession(BaseModel):
    ggis: GrantSetupGGIS | None = None
    name: GrantSetupName | None = None
    description: GrantSetupDescription | None = None
    contact: GrantSetupContact | None = None

    def to_session_dict(self) -> dict[str, Any]:
        """Convert to dict for session storage"""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> "GrantSetupSession":
        """Create from session dict with validation"""
        return cls.model_validate(session_data)
