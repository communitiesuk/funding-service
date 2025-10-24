from __future__ import annotations

import enum
import typing
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from app.common.collections.runner import FormRunner
    from app.common.data.models import Form, Question
    from app.deliver_grant_funding.forms import GroupDisplayOptionsForm, QuestionForm

scalars = str | int | float | bool | None
json_scalars = Dict[str, Any]
json_flat_scalars = Dict[str, scalars]

TRunnerUrlMap = dict[
    "FormRunnerState",
    Callable[["FormRunner", Optional["Question"], Optional["Form"], Optional["FormRunnerState"], Optional[int]], str],
]


class GrantStatusEnum(enum.StrEnum):
    DRAFT = "draft"
    LIVE = "live"


class RoleEnum(enum.StrEnum):
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
    TEXT_SINGLE_LINE = "Single line of text"
    TEXT_MULTI_LINE = "Multiple lines of text"
    EMAIL = "Email address"
    # todo: should we call this "A URL" or "A website address"
    URL = "Website address (URL)"
    INTEGER = "Whole number"
    YES_NO = "Yes or no"
    RADIOS = "Select one from a list (radios)"
    CHECKBOXES = "Select one or more from a list (checkboxes)"
    DATE = "A date"

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
    IS_BEFORE = "Is before"
    IS_AFTER = "Is after"
    BETWEEN_DATES = "Between dates"


class FormRunnerState(enum.StrEnum):
    TASKLIST = "tasklist"
    QUESTION = "question"
    CHECK_YOUR_ANSWERS = "check-your-answers"


class MultilineTextInputRows(IntEnum):
    SMALL = 3
    MEDIUM = 5
    LARGE = 10


class NumberInputWidths(enum.StrEnum):
    HUNDREDS = "govuk-input--width-3"
    THOUSANDS = "govuk-input--width-4"
    MILLIONS = "govuk-input--width-5"
    BILLIONS = "govuk-input--width-10"


# for now this is just used by the form but this could also be used to serialise the
# value used in the question presentation options and provide a consistent human readable value
class GroupDisplayOptions(enum.StrEnum):
    ONE_QUESTION_PER_PAGE = "one-question-per-page"
    ALL_QUESTIONS_ON_SAME_PAGE = "all-questions-on-same-page"


class QuestionPresentationOptions(BaseModel):
    # This is for radios (and maybe checkboxes) question types; the last item will be separated from the rest of the
    # data source items, visually by an 'or' break. It is meant to indicate that Other options are
    # appropriate and the user needs to fallback to some kind of 'not known' / 'Other' instead.
    last_data_source_item_is_distinct_from_others: bool | None = None

    # Multi-line text input
    # https://design-system.service.gov.uk/components/textarea/#use-appropriately-sized-textareas
    rows: MultilineTextInputRows | None = None
    # https://design-system.service.gov.uk/components/character-count/
    word_limit: int | None = None

    # Integer
    prefix: str | None = None
    suffix: str | None = None
    # https://design-system.service.gov.uk/components/text-input/#fixed-width-inputs
    width: NumberInputWidths | None = None

    # Groups
    show_questions_on_the_same_page: bool | None = None
    add_another_summary_line_question_ids: list[UUID] | None = None

    # Dates
    approximate_date: bool | None = None

    @staticmethod
    def from_question_form(form: "QuestionForm") -> QuestionPresentationOptions:
        match form._question_type:
            case QuestionDataType.RADIOS | QuestionDataType.CHECKBOXES:
                return QuestionPresentationOptions(
                    last_data_source_item_is_distinct_from_others=form.separate_option_if_no_items_match.data
                )
            case QuestionDataType.TEXT_MULTI_LINE:
                return QuestionPresentationOptions(
                    rows=form.rows.data,
                    word_limit=form.word_limit.data,
                )
            case QuestionDataType.INTEGER:
                return QuestionPresentationOptions(
                    prefix=form.prefix.data,
                    suffix=form.suffix.data,
                    width=form.width.data,
                )
            case QuestionDataType.DATE:
                return QuestionPresentationOptions(approximate_date=form.approximate_date.data)
            case _:
                return QuestionPresentationOptions()

    @staticmethod
    def from_group_form(form: "GroupDisplayOptionsForm") -> QuestionPresentationOptions:
        return QuestionPresentationOptions(
            show_questions_on_the_same_page=form.show_questions_on_the_same_page.data
            == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        )


class QuestionOptionsPostgresType(TypeDecorator):  # type: ignore[type-arg]
    impl = JSONB

    cache_ok = False

    def process_bind_param(self, value: BaseModel, dialect: Any) -> Any:  # type: ignore[override]
        if value is None:
            return None
        return value.model_dump(mode="json", exclude_none=True)

    def process_result_value(self, value: typing.Any, dialect: Any) -> QuestionPresentationOptions | None:
        if value is None:
            return None
        return QuestionPresentationOptions(**value)  # ty: ignore[missing-argument]


class ComponentType(enum.StrEnum):
    QUESTION = "QUESTION"
    GROUP = "GROUP"
