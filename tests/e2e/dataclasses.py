import dataclasses
import uuid
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, Union

from app.common.data.types import (
    CollectionType,
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
class DataProviderConfig:
    """A person invited to submit data (and optionally certify) on behalf of an organisation."""

    email: str
    full_name: str


@dataclasses.dataclass
class OrganisationConfig:
    """An organisation set up as a grant recipient."""

    name: str
    external_id: str
    type: str = "Central Government"
    grant_recipient_status: GrantRecipientStatusEnum = GrantRecipientStatusEnum.AWARDED
    # People invited to submit data for this organisation
    data_providers: list[DataProviderConfig] = dataclasses.field(default_factory=list)
    # Set first data provider as organisation's certifier
    set_certifiers: bool = True


@dataclasses.dataclass
class EligibilitySection:
    """Eligibility section when public sign up is enabled, plus which answer counts as eligible."""

    question: QuestionDict
    qualifying_answer: str

    def __post_init__(self) -> None:
        if self.question["type"] != QuestionDataType.YES_NO:
            raise ValueError("question must be a Yes/No question")


@dataclasses.dataclass
class CollectionConfig:
    """Spec for the collection built inside a `GrantScenario`."""

    name: str
    type: CollectionType = CollectionType.MONITORING_REPORT
    # Sections/questions to create in the collection
    sections: list[SectionDict] | None = None
    # Turn on self-serve sign up (requires type="application" + eligibility)
    enable_public_sign_up: bool = False
    # Required if enable_public_sign_up is set
    eligibility: EligibilitySection | None = None
    # Set reporting and submission dates
    set_dates: bool = False
    # Mark the collection as onboarding
    mark_onboarding: bool = False
    # Set a privacy policy
    set_privacy_policy: bool = False
    # Allow validation on this collection
    allow_validation: bool = False
    # Submissions won't need certifying before they're complete
    turn_off_requires_certification: bool = False
    # Make the grant and collection live/open
    set_live: bool = False

    def __post_init__(self) -> None:
        if self.enable_public_sign_up:
            if self.type != CollectionType.APPLICATION:
                raise ValueError("enable_public_sign_up requires type=CollectionType.APPLICATION")
            if self.eligibility is None:
                raise ValueError("enable_public_sign_up requires eligibility")


@dataclasses.dataclass
class GrantScenario:
    """Spec for `build_grant_scenario`: a grant is always built; everything else (collection,
    organisations, the heavier lifecycle steps) is opt-in, since most journeys only need a slice of this and
    shouldn't pay for the rest."""

    # The report/application built for this grant, if any
    collection: CollectionConfig | None = None
    # Organisations set up as recipients, each with their own data providers
    organisations: list[OrganisationConfig] = dataclasses.field(default_factory=list)
    # Invite and claim the shared grant-team-member identity on this grant
    add_grant_team_member: bool = False

    def __post_init__(self) -> None:
        if self.organisations and self.collection is None:
            raise ValueError("organisations requires a collection to be set")


@dataclasses.dataclass
class BuiltGrantScenario:
    """What `build_grant_scenario` built, returned for the test to use and for teardown to clean up."""

    grant_id: str
    grant_name: str
    # The raw uuid used to build grant_name/code, handy for admin search/cleanup
    grant_name_uuid: str
    collection_id: str | None
    org_names: list[str] = dataclasses.field(default_factory=list)
    # Set if the collection has public sign up enabled
    public_sign_up_url: str | None = None
