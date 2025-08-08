from __future__ import annotations

import enum
import typing
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from immutabledict import immutabledict
from pydantic import BaseModel
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

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
    EMAIL = "An email address"
    # todo: should we call this "A URL" or "A website address"
    URL = "A website address"
    TEXT_SINGLE_LINE = "A single line of text"
    TEXT_MULTI_LINE = "Multiple lines of text"
    INTEGER = "A whole number"
    YES_NO = "Yes or no"
    RADIOS = "Select one from a list of choices"
    CHECKBOXES = "Select one or more from a list of choices"

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


class TasklistTaskStatusEnum(enum.StrEnum):
    NOT_STARTED = SubmissionStatusEnum.NOT_STARTED.value
    IN_PROGRESS = SubmissionStatusEnum.IN_PROGRESS.value
    COMPLETED = SubmissionStatusEnum.COMPLETED.value

    if len(SubmissionStatusEnum) != 3:
        raise RuntimeError("Make sure this enum is updated if we add anything to SubmissionStatusEnum")

    NO_QUESTIONS = "No questions"


class SubmissionEventKey(enum.StrEnum):
    FORM_RUNNER_FORM_COMPLETED = "Form completed"
    SUBMISSION_SUBMITTED = "Submission submitted"


class CollectionType(enum.StrEnum):
    MONITORING_REPORT = "monitoring report"


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
    SPECIFICALLY = "Specifically"


class FormRunnerState(enum.StrEnum):
    TASKLIST = "tasklist"
    QUESTION = "question"
    CHECK_YOUR_ANSWERS = "check-your-answers"


class QuestionPresentationOptions(BaseModel):
    # This is for radios (and maybe checkboxes) question types; the last item will be separated from the rest of the
    # data source items, visually by an 'or' break. It is meant to indicate that none of the above options are
    # appropriate and the user needs to fallback to some kind of 'not known' / 'none of the above' instead.
    last_data_source_item_is_distinct_from_others: bool | None = None


class QuestionOptionsPostgresType(TypeDecorator):  # type: ignore[type-arg]
    impl = JSONB

    cache_ok = False

    def process_bind_param(self, value: BaseModel, dialect: Any) -> Any:  # type: ignore[override]
        if value is None:
            return None
        return value.model_dump(mode="json")

    def process_result_value(self, value: typing.Any, dialect: Any) -> QuestionPresentationOptions | None:
        if value is None:
            return None
        return QuestionPresentationOptions(**value)  # ty: ignore[missing-argument]


class ComponentType(enum.StrEnum):
    QUESTION = "QUESTION"
