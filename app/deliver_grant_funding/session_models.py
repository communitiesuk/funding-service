from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.expressions import ExpressionContext


class GrantSetupSession(BaseModel):
    has_ggis: Literal["yes", "no"] | None = None
    ggis_number: str = ""
    name: str = ""
    description: str = ""
    primary_contact_name: str = ""
    primary_contact_email: str = ""

    def to_session_dict(self) -> dict[str, Any]:
        """Convert to dict for session storage"""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> "GrantSetupSession":
        """Create from session dict with validation"""
        return cls.model_validate(session_data)


class AddContextToComponentSessionModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    data_type: QuestionDataType
    field: Literal["component"] = "component"
    component_form_data: dict[str, Any]

    data_source: ExpressionContext.ContextSources | None = None

    component_id: UUID | None = None
    parent_id: UUID | None = None


class AddContextToComponentGuidanceSessionModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    field: Literal["guidance"] = "guidance"
    component_form_data: dict[str, Any]

    component_id: UUID | None = None

    is_add_another_guidance: bool | None = False

    data_source: ExpressionContext.ContextSources | None = None


class AddContextToExpressionsModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    _prepared_form_data: dict[str, Any]

    field: ExpressionType
    managed_expression_name: ManagedExpressionsEnum
    expression_form_data: dict[str, Any]
    component_id: UUID

    data_source: ExpressionContext.ContextSources | None = None
    depends_on_question_id: UUID | None = None
    expression_id: UUID | None = None
