from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from immutabledict import immutabledict

if TYPE_CHECKING:
    from app.common.collections.runner import FormRunner
    from app.common.data.models import Form, Question

scalars = str | int | float | bool | None
json_scalars = Dict[str, Any]
json_flat_scalars = Dict[str, scalars]
immutable_json_flat_scalars = immutabledict[str, scalars]

TRunnerUrlMap = dict[
    "FormRunnerState",
    Callable[["FormRunner", Optional["Question"], Optional["Form"], Optional["FormRunnerState"]], str],
]


class RoleEnum(str, enum.Enum):
    ADMIN = (
        "admin"  # Admin level permissions, combines with null columns in UserRole table to denote level of admin access
    )
    MEMBER = "member"  # Basic read level permissions


# If a user roles implies they get other (lower) roles as well, list the role here with the roles they should get.
GRANT_ROLES_MAPPING = {
    RoleEnum.ADMIN: [role for role in RoleEnum],
}


class AuthMethodEnum(str, enum.Enum):
    SSO = "sso"
    MAGIC_LINK = "magic link"


class QuestionDataType(enum.StrEnum):
    # If adding values here, also update QuestionTypeForm
    # and manually create a migration to update question_type_enum in the db
    EMAIL = "An email address"
    TEXT_SINGLE_LINE = "A single line of text"
    TEXT_MULTI_LINE = "Multiple lines of text"
    INTEGER = "A whole number"
    YES_NO = "Yes or no"
    RADIOS = "Select one from a list of choices"

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
    IS_YES = "Yes"
    IS_NO = "No"
    ANY_OF = "Any of"


class FormRunnerState(enum.StrEnum):
    TASKLIST = "tasklist"
    QUESTION = "question"
    CHECK_YOUR_ANSWERS = "check-your-answers"
