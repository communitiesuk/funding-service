import dataclasses
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from app.common.data.types import GroupDisplayOptions, QuestionDataType, QuestionPresentationOptions
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import ManagedExpression


@dataclass
class E2ETestUser:
    email_address: str


@dataclass
class GuidanceText:
    heading: str
    body_heading: str
    body_link_text: str
    body_link_url: str
    body_ul_items: list[str]
    body_ol_items: list[str]


@dataclass
class E2ETestUserConfig:
    user_id: str
    email: str
    expected_login_url_pattern: str


@dataclasses.dataclass
class QuestionResponse:
    answer: str | list[str]
    error_message: str | None = None
    check_your_answers_text: str | None = None


@dataclasses.dataclass
class TextFieldWithData:
    prefix: str
    data_reference: DataReferenceConfig


@dataclasses.dataclass
class DataReferenceConfig:
    data_source: ExpressionContext.ContextSources
    question_text: str | None = None
    section_text: str | None = None
    collection_text: str | None = None


@dataclasses.dataclass
class E2EManagedExpression:
    managed_expression: ManagedExpression
    conditional_on: DataReferenceConfig | None = None
    # Note this assumes you're only referencing one question's answer in an expression, if two are needed for
    # Between/BetweenDates then this will need updating
    context_source: DataReferenceConfig | None = None


class QuestionDict(TypedDict):
    type: QuestionDataType
    text: str
    display_text: str
    hint: NotRequired[TextFieldWithData]  # Allows testing the 'Reference data' journey
    display_hint: NotRequired[str]  # For use with the 'Reference data' journey
    answers: list[QuestionResponse]
    choices: NotRequired[list[str]]
    options: NotRequired[QuestionPresentationOptions]
    guidance: NotRequired[GuidanceText]
    validation: NotRequired[E2EManagedExpression]
    condition: NotRequired[E2EManagedExpression]


class QuestionGroupDict(TypedDict):
    type: Literal["group"]
    text: str
    display_options: GroupDisplayOptions
    guidance: NotRequired[GuidanceText]
    condition: NotRequired[E2EManagedExpression]
    questions: list[QuestionDict]
