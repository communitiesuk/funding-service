import enum
from typing import Any, Dict

json_scalars = Dict[str, str | int | float | bool]


class RoleEnum(str, enum.Enum):
    ADMIN = (
        "admin"  # Admin level permissions, combines with null columns in UserRole table to denote level of admin access
    )
    MEMBER = "member"  # Basic read level permissions
    EDITOR = "editor"  # Read/write level permissions
    ASSESSOR = "assessor"  # Assessor level permissions
    S151_OFFICER = "s151_officer"  # S151 officer sign-off permissions


class QuestionDataType(enum.StrEnum):
    # If adding values here, also update QuestionTypeForm
    # and manually create a migration to update question_type_enum in the db
    TEXT_SINGLE_LINE = "A single line of text"
    TEXT_MULTI_LINE = "Multiple lines of text"
    INTEGER = "A whole number"

    @staticmethod
    def coerce(value: Any) -> "QuestionDataType":
        if isinstance(value, QuestionDataType):
            return value
        if isinstance(value, str):
            return QuestionDataType[value]
        raise ValueError(f"Cannot coerce {value} to QuestionDataType")


class CollectionStatusEnum(enum.StrEnum):
    NOT_STARTED = "Not started"
