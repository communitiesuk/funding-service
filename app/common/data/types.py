from __future__ import annotations

import enum
from typing import Any, Dict

from immutabledict import immutabledict

scalars = str | int | float | bool | None
json_scalars = Dict[str, Any]
json_flat_scalars = Dict[str, scalars]
immutable_json_flat_scalars = immutabledict[str, scalars]


class RoleEnum(str, enum.Enum):
    ADMIN = (
        "admin"  # Admin level permissions, combines with null columns in UserRole table to denote level of admin access
    )
    MEMBER = "member"  # Basic read level permissions


# If a user roles implies they get other (lower) roles as well, list the role here with the roles they should get.
GRANT_ROLES_MAPPING = {
    RoleEnum.ADMIN: [role for role in RoleEnum],
}


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


class SubmissionModeEnum(enum.StrEnum):
    TEST = "test"
    LIVE = "live"


class SubmissionStatusEnum(enum.StrEnum):
    NOT_STARTED = "Not started"
    IN_PROGRESS = "In progress"
    COMPLETED = "Completed"


class SubmissionEventKey(enum.StrEnum):
    FORM_RUNNER_FORM_COMPLETED = "Form completed"
    SUBMISSION_SUBMITTED = "Submission submitted"


class ExpressionType(enum.StrEnum):
    CONDITION = "CONDITION"
    VALIDATION = "VALIDATION"


class ManagedExpressionsEnum(enum.StrEnum):
    GREATER_THAN = "Greater than"
    LESS_THAN = "Less than"
    BETWEEN = "Between"
