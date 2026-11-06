import dataclasses
import uuid
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, Union

from app.common.data.types import (
    GrantRecipientStatusEnum,
    GroupDisplayOptions,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import EvaluatableExpression, ExpressionContext


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
    expect_group_validation_error: bool = False


@dataclasses.dataclass
class TextFieldWithData:
    prefix: str
    data_reference: DataReferenceConfig


@dataclasses.dataclass
class DataReferenceConfig:
    data_source: ExpressionContext.ContextSources | Literal["THIS_QUESTION"]
    question_text: str | None = None
    section_text: str | None = None
    collection_text: str | None = None
    data_set_name: str | None = None
    column_name: str | None = None


@dataclasses.dataclass
class E2EManagedExpression:
    evaluatable_expression: EvaluatableExpression
    conditional_on: DataReferenceConfig | None = None
    # Note this assumes you're only referencing one question's answer in an expression, if two are needed for
    # Between/BetweenDates then this will need updating
    context_source: DataReferenceConfig | None = None
    # TODO this is so that we can reference multiple fields in an expression.
    #  Need to refactor this class so we aren't duplicating where we put references
    expression_references: dict[str, DataReferenceConfig] | None = dataclasses.field(default_factory=dict)


class ReportDict(TypedDict):
    name: str
    id: uuid.UUID | None
    sections: list[SectionDict]
    require_certification: bool
    allow_multi_submissions: bool


class SectionDict(TypedDict):
    name: str
    components: list[TQuestionToTest]


class QuestionDict(TypedDict):
    type: QuestionDataType
    text: str
    display_text: str
    text_reference: NotRequired[DataReferenceConfig]
    hint: NotRequired[TextFieldWithData]  # Allows testing the 'Reference data' journey
    display_hint: NotRequired[str]  # For use with the 'Reference data' journey
    answers: list[QuestionResponse]
    choices: NotRequired[list[str]]
    options: NotRequired[QuestionPresentationOptions]
    data_options: NotRequired[QuestionDataOptions]
    guidance: NotRequired[GuidanceText]
    validation: NotRequired[E2EManagedExpression]
    condition: NotRequired[E2EManagedExpression]


class QuestionGroupDict(TypedDict):
    type: Literal["group"]
    text: str
    display_options: GroupDisplayOptions
    guidance: NotRequired[GuidanceText]
    condition: NotRequired[E2EManagedExpression]
    validation: NotRequired[E2EManagedExpression]
    questions: list[TQuestionToTest]
    add_another: NotRequired[bool]


TQuestionToTest = Union[QuestionDict, QuestionGroupDict]


@dataclasses.dataclass
class RecipientConfig:
    email: str
    full_name: str


@dataclasses.dataclass
class OrganisationConfig:
    name: str
    external_id: str
    type: str = "Central Government"


@dataclasses.dataclass
class GrantScenario:
    """Declarative spec for `build_grant_scenario`: a grant is always built; everything else (collection,
    organisation, recipient(s), the heavier lifecycle steps) is opt-in, since most journeys only need a slice
    of this and shouldn't pay for the rest."""

    collection_name: str | None = None
    collection_type: Literal["report", "application"] = "report"
    sections: list[SectionDict] | None = None
    enable_public_sign_up: bool = False
    eligibility_question: QuestionDict | None = None
    eligibility_qualifying_answer: str | None = None
    org_name: str | None = None
    org_external_id: str | None = None
    org_type: str = "Central Government"
    additional_organisations: list[OrganisationConfig] = dataclasses.field(default_factory=list)
    recipients: list[RecipientConfig] = dataclasses.field(default_factory=list)
    recipient_status: GrantRecipientStatusEnum = GrantRecipientStatusEnum.AWARDED
    set_certifiers: bool = False
    set_dates: bool = False
    mark_onboarding: bool = False
    set_privacy_policy: bool = False
    set_live: bool = False
    grant_team_member_email: str | None = None
    allow_validation: bool = False
    turn_off_requires_certification: bool = False

    def __post_init__(self) -> None:
        if bool(self.org_name) != bool(self.org_external_id):
            raise ValueError("org_name and org_external_id must be provided together")

        if self.additional_organisations and not self.org_name:
            raise ValueError("additional_organisations requires org_name/org_external_id to be set")

        needs_collection = (
            self.org_name
            or self.set_dates
            or self.mark_onboarding
            or self.set_privacy_policy
            or self.set_live
            or self.collection_type == "application"
            or bool(self.sections)
            or self.allow_validation
            or self.turn_off_requires_certification
        )
        if needs_collection and not self.collection_name:
            raise ValueError(
                "org_name/set_dates/mark_onboarding/set_privacy_policy/set_live/collection_type='application'/"
                "sections/allow_validation/turn_off_requires_certification all require collection_name to be set"
            )

        if self.enable_public_sign_up:
            if self.collection_type != "application":
                raise ValueError("enable_public_sign_up requires collection_type='application'")
            if not (self.eligibility_question and self.eligibility_qualifying_answer):
                raise ValueError(
                    "enable_public_sign_up requires eligibility_question and eligibility_qualifying_answer"
                )


@dataclasses.dataclass
class GrantScenarioHandle:
    grant_id: str
    grant_name: str
    grant_name_uuid: str
    collection_id: str | None
    report_name: str | None
    org_name: str | None
    additional_organisation_names: list[str] = dataclasses.field(default_factory=list)
    public_sign_up_url: str | None = None
