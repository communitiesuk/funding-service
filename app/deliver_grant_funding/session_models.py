from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field

from app.common.data.types import (
    DataSourceType,
    ExpressionType,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataType,
    TDataSetPreviewData,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.references import ExpressionReference

if TYPE_CHECKING:
    from app.common.data.models import Component


class GrantSetupSession(BaseModel):
    has_ggis: Literal["yes", "no"] | None = None
    ggis_number: str = ""
    name: str = ""
    code: str = ""
    description: str = ""
    primary_contact_name: str = ""
    primary_contact_email: str = ""

    def to_session_dict(self) -> dict[str, Any]:
        """Convert to dict for session storage"""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> GrantSetupSession:
        """Create from session dict with validation"""
        return cls.model_validate(session_data)


class _ReferenceDataSessionModel(BaseModel):
    def include_current_component_when_referencing_data(self, current_component: Component | None) -> bool:
        return False


class AddContextToComponentSessionModel(_ReferenceDataSessionModel):
    model_config = ConfigDict(validate_assignment=True)

    data_type: QuestionDataType
    field: Literal["component"] = "component"
    component_form_data: dict[str, Any]

    data_source: ExpressionContext.ContextSources | None = None

    component_id: UUID | None = None
    parent_id: UUID | None = None

    collection_id: UUID | None = None
    form_id: UUID | None = None


class AddContextToComponentGuidanceSessionModel(_ReferenceDataSessionModel):
    model_config = ConfigDict(validate_assignment=True)

    field: Literal["guidance"] = "guidance"
    component_form_data: dict[str, Any]

    component_id: UUID | None = None
    parent_id: UUID | None = None

    collection_id: UUID | None = None
    form_id: UUID | None = None

    is_add_another_guidance: bool | None = False

    data_source: ExpressionContext.ContextSources | None = None


class AddConditionDependsOnSessionModel(_ReferenceDataSessionModel):
    model_config = ConfigDict(validate_assignment=True)

    field: Literal["condition_depends_on"] = "condition_depends_on"
    component_id: UUID
    parent_id: UUID | None = None

    collection_id: UUID | None = None
    form_id: UUID | None = None

    data_source: ExpressionContext.ContextSources | None = None


class AddContextToExpressionsModel(_ReferenceDataSessionModel):
    model_config = ConfigDict(validate_assignment=True)

    _prepared_form_data: dict[str, Any]

    field: ExpressionType
    managed_expression_name: ManagedExpressionsEnum | None
    expression_form_data: dict[str, Any]

    component_id: UUID
    parent_id: UUID | None = None

    collection_id: UUID | None = None
    form_id: UUID | None = None

    data_source: ExpressionContext.ContextSources | None = None
    expression_id: UUID | None = None

    subject_reference: ExpressionReference | None = None

    is_custom: bool = False
    is_group: bool = False

    def include_current_component_when_referencing_data(self, current_component: Component | None) -> bool:
        if not current_component:
            return False

        target_expr_field_name = self.expression_form_data["add_context"]

        if (
            self.is_custom is True
            and target_expr_field_name == "custom_expression"
            and self.field == ExpressionType.VALIDATION
        ):
            return True

        return False


class DataSetColumnMapping(BaseModel):
    column_name: str
    column_type: Literal["TEXT", "BRITISH_POUNDS", "INTEGER", "DECIMAL"]
    prefix: str | None = Field(default_factory=lambda o: "£" if o["column_type"] == "BRITISH_POUNDS" else None)
    suffix: str | None = None
    max_decimal_places: int | None = Field(
        default_factory=lambda o: 2 if o["column_type"] == "BRITISH_POUNDS" else None
    )

    @property
    def data_type(self) -> Literal[QuestionDataType.TEXT_SINGLE_LINE, QuestionDataType.NUMBER]:
        match self.column_type:
            case "TEXT":
                return QuestionDataType.TEXT_SINGLE_LINE
            case "BRITISH_POUNDS" | "INTEGER" | "DECIMAL":
                return QuestionDataType.NUMBER
            case _:
                raise ValueError(f"Unknown column type: {self.column_type}")

    @property
    def number_type(self) -> NumberTypeEnum | None:
        match self.column_type:
            case "INTEGER":
                return NumberTypeEnum.INTEGER
            case "BRITISH_POUNDS" | "DECIMAL":
                return NumberTypeEnum.DECIMAL
            case _:
                return None

    @property
    def requires_manual_formatting(self) -> bool:
        return self.column_type in ["INTEGER", "DECIMAL"]


class DataSetUploadSessionModel(BaseModel):
    name: str
    data_source_type: DataSourceType
    data_columns: list[str]
    data_source_id: UUID4
    original_filename: str
    s3_key: str
    preview_data: TDataSetPreviewData
    column_mappings: list[DataSetColumnMapping] = Field(default_factory=list)
    has_missing_data: bool = False
    has_grant_recipient_mismatches: bool = False

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> DataSetUploadSessionModel:
        return cls.model_validate(session_data)

    def get_column_mapping(self, column_name: str) -> DataSetColumnMapping | None:
        return next((mapping for mapping in self.column_mappings if mapping.column_name == column_name), None)

    def has_columns_requiring_manual_formatting(self) -> bool:
        return any(mapping.requires_manual_formatting for mapping in self.column_mappings)
