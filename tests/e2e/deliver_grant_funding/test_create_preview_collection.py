import datetime
import re
import uuid
from decimal import Decimal
from typing import Union

import pytest
from playwright.sync_api import Locator, Page, expect

from app import NumberTypeEnum
from app.common.data.types import (
    GroupDisplayOptions,
    ManagedExpressionsEnum,
    MultilineTextInputRows,
    NumberInputWidths,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import (
    AnyOf,
    Between,
    BetweenDates,
    GreaterThan,
    IsNo,
    IsYes,
    LessThan,
    Specifically,
    UKPostcode,
)
from app.common.filters import format_thousands
from tests.e2e.access_grant_funding.pages import AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import (
    DeliverGrantFundingUserType,
    e2e_user_configs,
    login_with_session_cookie,
    login_with_stub_sso,
)
from tests.e2e.dataclasses import (
    DataReferenceConfig,
    E2EManagedExpression,
    E2ETestUser,
    GuidanceText,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    TextFieldWithData,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDashboardPage, GrantDetailsPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AddQuestionDetailsPage,
    AdminReportingLifecycleTasklistPage,
    DeliverTestGrantRecipientJourneyPage,
    EditQuestionGroupPage,
    EditQuestionPage,
    GrantReportsPage,
    ManageSectionPage,
    MarkAsOnboardingWithFundingServicePage,
    OverrideGrantRecipientCertifiersPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    ReportSectionsPage,
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
    RunnerTasklistPage,
    SetPrivacyPolicyPage,
    SetReportingDatesPage,
    SetUpDataProvidersPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
    SetUpTestGrantRecipientsPage,
    SetUpTestGrantRecipientUsersPage,
    _reference_data_flow,
)
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
    delete_test_org_through_admin,
)


def extract_uuid_from_url(url: str, pattern: str) -> str:
    """Extract a UUID from a URL using a regex pattern.

    The pattern should contain a named group 'uuid' for the UUID to extract.
    Example: r"/grant/(?P<uuid>[a-f0-9-]+)/reports"
    """
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Could not extract UUID from URL {url} using pattern {pattern}")
    return match.group("uuid")


TQuestionToTest = Union[QuestionDict, QuestionGroupDict]


section_1_questions_with_groups_to_test: dict[str, TQuestionToTest] = {
    "yes-no": {
        "type": QuestionDataType.YES_NO,
        "text": "Do you want to show question groups?",
        "display_text": "Do you want to show question groups?",
        "answers": [
            QuestionResponse("Yes"),
        ],
    },
    "show-cross-section-conditional": {
        "type": QuestionDataType.NUMBER,
        "text": "What number do you want to see in another section?",
        "display_text": "What number do you want to see in another section?",
        "options": QuestionPresentationOptions(),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        "answers": [
            QuestionResponse("100"),
        ],
    },
    "question-group-all-same-page": {
        "type": "group",
        "text": "This is a question group",
        "display_options": GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
        "guidance": GuidanceText(
            heading="This is a guidance page heading for a group",
            body_heading="Guidance subheading",
            body_link_text="Design system link text",
            body_link_url="https://design-system.service.gov.uk",
            body_ul_items=["UL item one", "UL item two"],
            body_ol_items=["OL item one", "OL item two"],
        ),
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION,
                question_text="Do you want to show question groups?",
            ),
            managed_expression=IsYes(question_id=uuid.uuid4()),
        ),
        "questions": [
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "Group Enter a single line of text",
                "display_text": "Group Enter a single line of text",
                "answers": [QuestionResponse("E2E question text single line")],
            },
            {
                "type": QuestionDataType.URL,
                "text": "Group Enter a website address",
                "display_text": "Group Enter a website address",
                "answers": [
                    QuestionResponse("https://gov.uk"),
                ],
            },
            {
                "type": QuestionDataType.EMAIL,
                "text": "Group Enter an email address",
                "display_text": "Group Enter an email address",
                "answers": [
                    QuestionResponse("group@example.com"),
                ],
            },
        ],
    },
    "text-single-line": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "Enter another single line of text",
        "display_text": "Enter another single line of text",
        "answers": [QuestionResponse("E2E question text single line second answer")],
    },
    "question-group-one-per-page": {
        "type": "group",
        "text": "One question per page group",
        "display_options": GroupDisplayOptions.ONE_QUESTION_PER_PAGE,
        "questions": [
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "Second group Enter a single line of text",
                "display_text": "Second group Enter a single line of text",
                "answers": [QuestionResponse("E2E question text single line group")],
            },
            {
                "type": QuestionDataType.EMAIL,
                "text": "Second group Enter an email address",
                "display_text": "Second group Enter an email address",
                "answers": [
                    QuestionResponse("group2@example.com"),
                ],
            },
            {
                "type": "group",
                "text": "Nested Group",
                "display_options": GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
                "questions": [
                    {
                        "type": QuestionDataType.TEXT_SINGLE_LINE,
                        "text": "Nested group single line of text",
                        "display_text": "Nested group single line of text",
                        "answers": [QuestionResponse("E2E question text single line nested group")],
                    },
                    {
                        "type": QuestionDataType.EMAIL,
                        "text": "Nested group Enter an email address",
                        "display_text": "Nested group Enter an email address",
                        "answers": [
                            QuestionResponse("nested_group@example.com"),
                        ],
                    },
                ],
            },
        ],
    },
}


section_2_questions_to_test: dict[str, TQuestionToTest] = {
    "date": QuestionDict(
        type=QuestionDataType.DATE,
        text="Enter a date",
        display_text="Enter a date",
        answers=[
            QuestionResponse(
                ["2003", "2", "01"],
                "The answer must be between 1 January 2020 (inclusive) and 1 January 2025 (exclusive)",
            ),
            QuestionResponse(answer=["2022", "04", "05"], check_your_answers_text="5 April 2022"),
        ],
        validation=E2EManagedExpression(
            managed_expression=BetweenDates(
                question_id=uuid.uuid4(),
                earliest_value=datetime.date(2020, 1, 1),
                earliest_inclusive=True,
                latest_value=datetime.date(2025, 1, 1),
                latest_inclusive=False,
            )
        ),
    ),
    "approx_date": QuestionDict(
        type=QuestionDataType.DATE,
        text="Enter an approximate date",
        display_text="Enter an approximate date",
        hint=TextFieldWithData(
            prefix="You entered an exact date of",
            data_reference=DataReferenceConfig(ExpressionContext.ContextSources.SECTION, question_text="Enter a date"),
        ),
        display_hint="You entered an exact date of Tuesday 5 April 2022",
        answers=[
            QuestionResponse(
                ["2003", "2"],
                "The answer must be between April 2020 (inclusive) and March 2022 (exclusive)",
            ),
            QuestionResponse(["2021", "04"], check_your_answers_text="April 2021"),
        ],
        options=QuestionPresentationOptions(approximate_date=True),
        validation=E2EManagedExpression(
            managed_expression=BetweenDates(
                question_id=uuid.uuid4(),
                earliest_value=datetime.date(2020, 4, 1),
                earliest_inclusive=True,
                latest_value=datetime.date(2022, 3, 1),
                latest_inclusive=False,
            )
        ),
    ),
    "prefix-integer": {
        "type": QuestionDataType.NUMBER,
        "text": "Enter the total cost as a number",
        "display_text": "Enter the total cost as a number",
        "answers": [
            QuestionResponse("0", "The answer must be greater than 1"),
            QuestionResponse("10000"),
        ],
        "options": QuestionPresentationOptions(prefix="£", width=NumberInputWidths.BILLIONS, approximate_date=True),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        "validation": E2EManagedExpression(
            managed_expression=GreaterThan(question_id=uuid.uuid4(), minimum_value=1, inclusive=False)
        ),
        "condition": E2EManagedExpression(
            managed_expression=BetweenDates(
                question_id=uuid.uuid4(),
                earliest_value=datetime.date(2020, 4, 1),
                earliest_inclusive=False,
                latest_value=None,
                latest_expression="",
                latest_inclusive=False,
            ),
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter an approximate date"
            ),
            context_source=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter a date"
            ),
        ),
    },
    "suffix-integer": {
        "type": QuestionDataType.NUMBER,
        "text": "Enter the total weight as a number",
        "display_text": "Enter the total weight as a number",
        "answers": [
            QuestionResponse("10001", "The answer must be less than or equal to £10,000"),
            QuestionResponse("100"),
        ],
        "options": QuestionPresentationOptions(suffix="kg", width=NumberInputWidths.HUNDREDS),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        "validation": E2EManagedExpression(
            managed_expression=LessThan(
                question_id=uuid.uuid4(),
                maximum_value=None,
                maximum_expression="",
                inclusive=True,
            ),
            context_source=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter the total cost as a number"
            ),
        ),  # question_id does not matter here
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter the total cost as a number"
            ),
            managed_expression=GreaterThan(question_id=uuid.uuid4(), minimum_value=1, inclusive=False),
        ),
    },
    "between-integer": {
        "type": QuestionDataType.NUMBER,
        "text": "Enter a number between 20 and 100",
        "display_text": "Enter a number between 20 and 100",
        "answers": [
            QuestionResponse("101", "The answer must be between 20 (inclusive) and 100 (exclusive)"),
            QuestionResponse("20"),
        ],
        "options": QuestionPresentationOptions(),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        "validation": E2EManagedExpression(
            managed_expression=Between(
                question_id=uuid.uuid4(),
                maximum_value=100,
                maximum_inclusive=False,
                minimum_value=20,
                minimum_inclusive=True,
            )
        ),  # question_id does not matter here
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter the total weight as a number"
            ),
            managed_expression=LessThan(question_id=uuid.uuid4(), maximum_value=100, inclusive=True),
        ),
    },
    "suffix-decimal": {
        "type": QuestionDataType.NUMBER,
        "text": "Enter the percentage of employees involved in this project",
        "display_text": "Enter the percentage of employees involved in this project",
        "answers": [
            QuestionResponse("1,250.4", "The answer must be less than or equal to 100"),
            QuestionResponse("50.423", "The answer cannot be more than 2 decimal places"),
            QuestionResponse("35.67"),
        ],
        "options": QuestionPresentationOptions(suffix="%", width=NumberInputWidths.BILLIONS),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
        "validation": E2EManagedExpression(
            managed_expression=LessThan(question_id=uuid.uuid4(), maximum_value=100, inclusive=True)
        ),
    },
    "between-decimal": {
        "type": QuestionDataType.NUMBER,
        "text": "Enter the number with 5 decimal places",
        "display_text": "Enter the number with 5 decimal places",
        "answers": [
            QuestionResponse("1.12346", "The answer must be between 0.22334 (exclusive) and 1.12345 (inclusive)"),
            QuestionResponse("1.123456", "The answer cannot be more than 5 decimal places"),
            QuestionResponse("0.22333", "The answer must be between 0.22334 (exclusive) and 1.12345 (inclusive)"),
            QuestionResponse("0.45678"),
        ],
        "options": QuestionPresentationOptions(),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=5),
        "validation": E2EManagedExpression(
            managed_expression=Between(
                question_id=uuid.uuid4(),
                maximum_value=Decimal("1.12345"),
                maximum_inclusive=True,
                minimum_value=Decimal("0.22334"),
                minimum_inclusive=False,
            )
        ),
    },
    "yes-no": {
        "type": QuestionDataType.YES_NO,
        "text": "Yes or no",
        "display_text": "Yes or no",
        "answers": [
            QuestionResponse("Yes"),
        ],
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter a number between 20 and 100"
            ),
            managed_expression=Between(
                question_id=uuid.uuid4(),
                maximum_value=40,
                maximum_inclusive=True,
                minimum_value=15,
                minimum_inclusive=False,
            ),
        ),
    },
    "radio": {
        "type": QuestionDataType.RADIOS,
        "text": "Select an option",
        "display_text": "Select an option",
        "choices": ["option 1", "option 2", "option 3"],
        "answers": [
            QuestionResponse("option 2"),
        ],
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Yes or no"
            ),
            managed_expression=IsYes(question_id=uuid.uuid4()),
        ),
    },
    "autocomplete": {
        "type": QuestionDataType.RADIOS,
        "text": "Select an option from the accessible autocomplete",
        "display_text": "Select an option from the accessible autocomplete",
        "choices": [f"option {x}" for x in range(1, 30)],
        "answers": [
            QuestionResponse("Other"),
        ],
        "options": QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Select an option"
            ),
            managed_expression=AnyOf(
                question_id=uuid.uuid4(),
                items=[{"key": "option-2", "label": "option 2"}, {"key": "option-3", "label": "option 3"}],
            ),
        ),
    },
    "checkboxes": {
        "type": QuestionDataType.CHECKBOXES,
        "text": "Select one or more options",
        "display_text": "Select one or more options",
        "choices": ["option 1", "option 2", "option 3", "option 4"],
        "answers": [
            QuestionResponse(["option 2", "option 3"]),
        ],
        "options": QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION,
                question_text="Select an option from the accessible autocomplete",
            ),
            managed_expression=AnyOf(question_id=uuid.uuid4(), items=[{"key": "other", "label": "Other"}]),
        ),
    },
    "email": {
        "type": QuestionDataType.EMAIL,
        "text": "Enter an email address",
        "display_text": "Enter an email address",
        "answers": [
            QuestionResponse("not-an-email", "Enter an email address in the correct format, like name@example.com"),
            QuestionResponse("name@example.com"),
        ],
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Select one or more options"
            ),
            managed_expression=Specifically(question_id=uuid.uuid4(), item={"key": "option-2", "label": "option 2"}),
        ),
    },
    "postcode": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "Enter a postcode",
        "display_text": "Enter a postcode",
        "answers": [
            QuestionResponse("E2E question text single line", "The answer must be a UK postcode"),
            QuestionResponse("SW1A 1AA"),
        ],
        "validation": E2EManagedExpression(
            managed_expression=UKPostcode(
                question_id=uuid.uuid4(),
            )
        ),  # question_id does not matter here
        "guidance": GuidanceText(
            heading="This is a guidance page heading",
            body_heading="Guidance subheading",
            body_link_text="Design system link text",
            body_link_url="https://design-system.service.gov.uk",
            body_ul_items=["UL item one", "UL item two"],
            body_ol_items=["OL item one", "OL item two"],
        ),
    },
    "text-multi-line": {
        "type": QuestionDataType.TEXT_MULTI_LINE,
        "text": "Enter a few lines of text",
        "display_text": "Enter a few lines of text",
        "answers": [
            QuestionResponse("E2E question text multi line\nwith a second line that's over the word limit"),
            QuestionResponse("E2E question text multi line\nwith a second line"),
        ],
        "options": QuestionPresentationOptions(word_limit=10, rows=MultilineTextInputRows.LARGE),
    },
    "url": {
        "type": QuestionDataType.URL,
        "text": "Enter a website address",
        "display_text": "Enter a website address",
        "answers": [
            QuestionResponse("not-a-url", "Enter a website address in the correct format, like www.gov.uk"),
            QuestionResponse("https://gov.uk"),
        ],
    },
    "file-upload": {
        "type": QuestionDataType.FILE_UPLOAD,
        "text": "Upload a supporting document",
        "display_text": "Upload a supporting document",
        "answers": [
            # ./tests/fixtures/e2e-test-file.txt
            QuestionResponse("e2e-test-file.txt"),
        ],
    },
    "text-single-line-not-shown": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "This question should not be shown",
        "display_text": "This question should not be shown",
        "answers": [QuestionResponse("This question shouldn't be shown")],
        "condition": E2EManagedExpression(
            conditional_on=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.SECTION, question_text="Yes or no"
            ),
            managed_expression=IsNo(question_id=uuid.uuid4()),
        ),
    },
    "cross-section-reference": {
        "type": QuestionDataType.NUMBER,
        "text": "Prove that referencing data from another section works",
        "display_text": "Prove that referencing data from another section works",
        "hint": TextFieldWithData(
            prefix="You entered this in the last section: ",
            data_reference=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.PREVIOUS_SECTION,
                section_text="E2E first task - grouped questions",
                question_text="What number do you want to see in another section?",
            ),
        ),
        "display_hint": "You entered this in the last section: 100",
        "options": QuestionPresentationOptions(),
        "data_options": QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        "answers": [
            QuestionResponse("500", "The answer must be less than 100"),
            QuestionResponse("50"),
        ],
        "validation": E2EManagedExpression(
            managed_expression=LessThan(
                question_id=uuid.uuid4(), maximum_value=None, maximum_expression="", inclusive=False
            ),
            context_source=DataReferenceConfig(
                data_source=ExpressionContext.ContextSources.PREVIOUS_SECTION,
                section_text="E2E first task - grouped questions",
                question_text="What number do you want to see in another section?",
            ),
        ),
    },
}


def create_grant(new_grant_name: str, grant_name_uuid: str, all_grants_page: AllGrantsPage) -> GrantDashboardPage:
    grant_intro_page = all_grants_page.click_set_up_a_grant()
    grant_ggis_page = grant_intro_page.click_continue()
    grant_ggis_page.select_yes()
    grant_ggis_page.fill_ggis_number()
    grant_name_page = grant_ggis_page.click_save_and_continue()
    grant_name_page.fill_name(new_grant_name)
    grant_code_page = grant_name_page.click_save_and_continue()
    grant_code_page.fill_code(f"E2E-{grant_name_uuid[:8].upper()}")
    grant_description_page = grant_code_page.click_save_and_continue()
    new_grant_description = f"Description for {new_grant_name}"
    grant_description_page.fill_description(new_grant_description)
    grant_contact_page = grant_description_page.click_save_and_continue()
    grant_contact_page.fill_contact_name()
    grant_contact_page.fill_contact_email()
    grant_check_your_answers_page = grant_contact_page.click_save_and_continue()
    grant_dashboard_page = grant_check_your_answers_page.click_add_grant()
    return grant_dashboard_page


def create_question_or_group(
    question_definition: TQuestionToTest,
    manage_section_page: ManageSectionPage | EditQuestionGroupPage,
    parent_group_name: str | None = None,
):
    if question_definition["type"] == "group":
        add_question_group_page = manage_section_page.click_add_question_group(question_definition["text"])
        add_question_group_page.fill_in_question_group_name()
        group_display_options_page = add_question_group_page.click_continue()
        group_display_options_page.click_question_group_display_type(question_definition["display_options"])

        add_another_options_page = group_display_options_page.click_submit()
        add_another_options_page.click_add_another(False)
        edit_question_group_page = add_another_options_page.click_submit(parent_group_name)
        if (
            question_definition.get("guidance") is not None
            and question_definition.get("display_options") == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        ):
            add_question_guidance(question_definition, edit_question_group_page)
        if question_definition.get("condition") is not None:
            add_condition(edit_question_group_page, question_definition["condition"])
        for question in question_definition["questions"]:
            create_question_or_group(question, edit_question_group_page, parent_group_name=question_definition["text"])
        if parent_group_name:
            edit_question_group_page.click_parent_group_breadcrumb()
        else:
            edit_question_group_page.click_section_breadcrumb()
    else:
        create_question(question_definition, manage_section_page, parent_group_name=parent_group_name)


def _assert_reports_breadcrumb_layout(page: Page, parent_group_name: str | None = None) -> None:
    breadcrumbs = page.locator("a.govuk-breadcrumbs__link")
    if not parent_group_name:
        expect(breadcrumbs).to_have_count(3)
        expect(page.get_by_text("question group hidden ...")).not_to_be_visible()
    elif parent_group_name == "This is a question group" or parent_group_name == "One question per page group":
        expect(breadcrumbs).to_have_count(4)
        expect(page.get_by_text("question group hidden ...")).not_to_be_visible()
    elif parent_group_name == "Nested Group":
        expect(breadcrumbs).to_have_count(4)
        expect(page.get_by_text("question group hidden ...")).to_be_visible()


def create_question(
    question_definition: TQuestionToTest,
    manage_page: ManageSectionPage | EditQuestionGroupPage,
    parent_group_name: str = None,
) -> None:
    question_type_page = manage_page.click_add_question()
    question_type_page.click_question_type(question_definition["type"])
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_definition["type"].value, exact=True)).to_be_visible()
    question_text = question_definition["text"]
    expect(
        question_details_page.page.locator(".app-context-aware-editor__visible-textarea[id='text']")
    ).to_be_attached()
    expect(
        question_details_page.page.locator(".app-context-aware-editor__visible-textarea[id='hint']")
    ).to_be_attached()

    if question_definition["type"] == QuestionDataType.NUMBER:
        question_details_page.select_number_type(question_definition["data_options"].number_type)
        if question_definition["data_options"].number_type == NumberTypeEnum.DECIMAL:
            question_details_page.fill_max_number_of_decimal_places(
                question_definition["data_options"].max_decimal_places
            )

    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(question_text.lower())

    if hint := question_definition.get("hint"):
        question_details_page.fill_question_hint(hint.prefix)
        select_data_source_page = question_details_page.click_insert_data(field_name="hint")
        _reference_data_flow(select_data_source_page, hint.data_reference)
    else:
        question_details_page.fill_question_hint(f"Hint text for: {question_text}")

    if question_definition["type"] in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
        question_details_page.fill_data_source_items(question_definition["choices"])

        options = question_definition.get("options")
        if options is not None and options.last_data_source_item_is_distinct_from_others is not None:
            question_details_page.click_other_option_checkbox()
            question_details_page.enter_other_option_text()

    if (
        question_definition["type"]
        in [QuestionDataType.NUMBER, QuestionDataType.TEXT_MULTI_LINE, QuestionDataType.DATE]
        and question_definition.get("options") is not None
    ):
        add_advanced_formatting(question_definition, question_details_page)

    edit_question_page = question_details_page.click_submit()

    _assert_reports_breadcrumb_layout(edit_question_page.page, parent_group_name=parent_group_name)

    if question_definition.get("guidance") is not None:
        add_question_guidance(question_definition, edit_question_page)
    if question_definition.get("validation") is not None:
        add_validation(
            edit_question_page,
            question_definition["validation"],
            question_definition.get("options", None),
        )
    if question_definition.get("condition") is not None:
        add_condition(edit_question_page, question_definition["condition"], question_definition.get("options", None))

    if isinstance(manage_page, EditQuestionGroupPage):
        edit_question_page.click_question_group_breadcrumb(manage_page.group_name)
    else:
        edit_question_page.click_section_breadcrumb()


def add_advanced_formatting(
    question_definition: TQuestionToTest, question_details_page: AddQuestionDetailsPage
) -> None:
    options = question_definition.get("options")
    question_details_page.click_advanced_formatting_options()
    match question_definition["type"]:
        case QuestionDataType.TEXT_MULTI_LINE:
            if options.rows is not None:
                question_details_page.select_multiline_input_rows(options.rows)
            if options.word_limit is not None:
                question_details_page.fill_word_limit(options.word_limit)
        case QuestionDataType.NUMBER:
            if options.prefix is not None:
                question_details_page.fill_prefix(options.prefix)
            if options.suffix is not None:
                question_details_page.fill_suffix(options.suffix)
            if options.width is not None:
                question_details_page.select_input_width(options.width)
        case QuestionDataType.DATE:
            if options.approximate_date is True:
                question_details_page.click_is_approximate_date_checkbox()
        case _:
            pass  # No advanced formatting for other question types


def add_question_guidance(
    question_definition: TQuestionToTest, edit_question_page: EditQuestionPage | EditQuestionGroupPage
) -> None:
    guidance = question_definition.get("guidance")
    if guidance is not None:
        add_guidance_page = edit_question_page.click_add_guidance()
        add_guidance_page.fill_guidance_heading(guidance.heading)
        expect(
            add_guidance_page.page.locator(".app-context-aware-editor__visible-textarea[id='guidance_body']")
        ).to_be_attached()
        add_guidance_page.fill_guidance_default()
        edit_question_page = add_guidance_page.click_save_guidance_button(edit_question_page)
        expect(edit_question_page.page.get_by_text("Page heading", exact=True)).to_be_visible()
        expect(edit_question_page.page.get_by_text("Guidance text", exact=True)).to_be_visible()
        edit_question_page.click_change_guidance()
        add_guidance_page.fill_guidance(guidance)
        add_guidance_page.click_save_guidance_button(edit_question_page)


def add_validation(
    edit_question_page: EditQuestionPage,
    validation: E2EManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    add_validation_page = edit_question_page.click_add_validation()
    add_validation_page.configure_managed_validation(
        validation.managed_expression, validation.context_source, presentation_options
    )
    edit_question_page = add_validation_page.click_add_validation()


def add_condition(
    edit_question_page: EditQuestionPage | EditQuestionGroupPage,
    condition: E2EManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    add_condition_page = edit_question_page.click_add_condition()
    select_data_source_page = add_condition_page.click_reference_data_button()
    _reference_data_flow(select_data_source_page, condition.conditional_on)
    add_condition_page.configure_managed_condition(
        condition.managed_expression, condition.context_source, presentation_options
    )
    add_condition_page.click_add_condition(edit_question_page)


def complete_question_group(
    question_page: RunnerQuestionPage,
    tasklist_page: RunnerTasklistPage,
    grant_name: str,
    group_to_test: TQuestionToTest,
):
    if group_to_test.get("guidance") is not None:
        assert_question_visibility(question_page, group_to_test)
    for nested_question in group_to_test["questions"]:
        if group_to_test.get("guidance") is None:
            question_page = RunnerQuestionPage(
                tasklist_page.page,
                tasklist_page.domain,
                grant_name,
                nested_question["text"],
                is_in_a_same_page_group=group_to_test["display_options"]
                == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
            )
            assert_question_visibility(question_page, nested_question)
        if nested_question["type"] == "group":
            complete_question_group(question_page, tasklist_page, grant_name, nested_question)
        else:
            for question_response in nested_question["answers"]:
                question_page.respond_to_question(
                    question_type=nested_question["type"],
                    question_text=nested_question["display_text"],
                    answer=question_response.answer,
                )
        if group_to_test["display_options"] == GroupDisplayOptions.ONE_QUESTION_PER_PAGE:
            question_page.click_continue()
    if group_to_test["display_options"] == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE:
        question_page.click_continue()


def complete_task(
    tasklist_page: RunnerTasklistPage, section_name: str, grant_name: str, questions_to_test: dict[str, TQuestionToTest]
) -> None:
    tasklist_page.click_on_section(section_name=section_name)
    for question_to_test in questions_to_test.values():
        question_page = RunnerQuestionPage(
            tasklist_page.page,
            tasklist_page.domain,
            grant_name,
            question_to_test.get("display_text", question_to_test["text"]),
        )

        if question_to_test["type"] == "group":
            complete_question_group(question_page, tasklist_page, grant_name, question_to_test)
        else:
            assert_question_visibility(question_page, question_to_test)
            for question_response in question_to_test["answers"]:
                if "This question should not be shown" not in question_to_test["display_text"]:
                    question_page.respond_to_question(
                        question_type=question_to_test["type"],
                        question_text=question_to_test["display_text"],
                        answer=question_response.answer,
                    )
                    question_page.click_continue()

                    if question_response.error_message:
                        expect(
                            question_page.page.get_by_role("link", name=question_response.error_message)
                        ).to_be_visible()


def task_check_your_answers(
    tasklist_page: RunnerTasklistPage, grant_name: str, report_name: str, questions_to_test: dict[str, TQuestionToTest]
):
    check_your_answers_page = RunnerCheckYourAnswersPage(tasklist_page.page, tasklist_page.domain, grant_name)

    def _assert_check_your_answers(questions_to_check: list[TQuestionToTest]):
        for question_to_check in questions_to_check:
            if question_to_check["type"] == "group":
                _assert_check_your_answers(question_to_check["questions"])
            else:
                assert_check_your_answers(check_your_answers_page, question_to_check)

    _assert_check_your_answers(list(questions_to_test.values()))

    expect(check_your_answers_page.page.get_by_text("Have you completed this section?", exact=True)).to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)


def navigate_to_report_sections_page(page: Page, domain: str, grant_name: str, report_name: str) -> ReportSectionsPage:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    report_sections_page = grant_reports_page.click_manage_sections(grant_name=grant_name, report_name=report_name)
    return report_sections_page


def assert_question_visibility(question_page: RunnerQuestionPage, question_to_test: TQuestionToTest) -> None:
    if display_hint := question_to_test.get("display_hint"):
        expect(question_page.page.locator(".govuk-hint", has_text=display_hint)).to_be_visible()

    if question_to_test.get("guidance") is None:
        if "This question should not be shown" in question_to_test["text"]:
            expect(question_page.heading).not_to_be_visible()
        else:
            expect(question_page.heading).to_be_visible()
    else:
        expect(question_page.page.get_by_role("heading", name=question_to_test["guidance"].heading)).to_be_visible()
        expect(
            question_page.page.get_by_role("heading", name=question_to_test["guidance"].body_heading)
        ).to_be_visible()
        expect(question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)).to_be_visible()
        expect(
            question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)
        ).to_have_attribute("href", question_to_test["guidance"].body_link_url)
        for item in question_to_test["guidance"].body_ul_items:
            expect(question_page.page.locator("ul").get_by_text(item)).to_be_visible()
        for item in question_to_test["guidance"].body_ol_items:
            expect(question_page.page.locator("ol").get_by_text(item)).to_be_visible()


def assert_check_your_answers(check_your_answers_page: RunnerCheckYourAnswersPage, question: TQuestionToTest) -> None:
    if "This question should not be shown" in question["text"]:
        return

    question_heading = check_your_answers_page.page.get_by_text(question["display_text"], exact=True)
    expect(question_heading).to_be_visible()

    question_name = question["text"].lower()
    if question["type"] == QuestionDataType.CHECKBOXES:
        checkbox_answers_list = check_your_answers_page.page.get_by_test_id(f"answer-{question_name}").locator("li")
        expect(checkbox_answers_list).to_have_text(question["answers"][-1].answer)
    elif question["type"] == QuestionDataType.NUMBER:
        answer_to_format = (
            int(question["answers"][-1].answer)
            if question["data_options"].number_type == NumberTypeEnum.INTEGER
            else Decimal(question["answers"][-1].answer)
        )
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            f"{question['options'].prefix or ''}{format_thousands(answer_to_format)}{question['options'].suffix or ''}"
        )
    elif question["type"] == QuestionDataType.DATE:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            question["answers"][-1].check_your_answers_text
        )
    else:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            question["answers"][-1].answer
        )


def assert_check_your_answer_for_all_questions(questions_to_check: list[TQuestionToTest], report_answers_list: Locator):
    for question_to_check in questions_to_check:
        if question_to_check["type"] == "group":
            assert_check_your_answer_for_all_questions(question_to_check["questions"], report_answers_list)
        else:
            assert_check_your_answer_for_question(question_to_check, report_answers_list)


def assert_check_your_answer_for_question(question: TQuestionToTest, answers_list: Locator) -> None:
    # TODO Can we combine this with the logic in assert_check_your_answers? Feels like duplication
    if "This question should not be shown" in question["text"]:
        return
    if question["type"] == QuestionDataType.CHECKBOXES:
        expect(
            answers_list.get_by_text(f"{question['text']} {' '.join(question['answers'][-1].answer)}", exact=True)
        ).to_be_visible()
    elif question["type"] == QuestionDataType.NUMBER:
        expect(
            answers_list.get_by_text(
                f"{question['text']} {question['options'].prefix or ''}"
                f"{format_thousands(int(question['answers'][-1].answer))}{question['options'].suffix or ''}",
                exact=True,
            )
        ).to_be_visible()
    elif question["type"] == QuestionDataType.DATE:
        expect(answers_list.get_by_text(question["answers"][-1].check_your_answers_text, exact=True)).to_be_visible()
    else:
        expect(
            answers_list.get_by_text(f"{question['text']} {question['answers'][-1].answer}", exact=True)
        ).to_be_visible()


def switch_user(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    user_type: DeliverGrantFundingUserType,
    email_address: str,
) -> E2ETestUser:
    grant_dashboard_page = GrantDashboardPage(page, domain)
    grant_dashboard_page.click_sign_out()
    if e2e_test_secrets.E2E_ENV == "local":
        return login_with_stub_sso(domain, page, email_address, user_type)
    else:
        return login_with_session_cookie(page, domain, e2e_test_secrets, user_type)


# Module-level storage for shared test data across dependent tests
_shared_setup_data: dict | None = None


def test_setup_grant_and_collection(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Setup test: creates grant and collection with all question types."""
    global _shared_setup_data

    grant_name_uuid = str(uuid.uuid4())

    # Sense check that the test includes all question types
    assert (
        len(QuestionDataType) == 10
        and len(section_2_questions_to_test) == 18
        and len(ManagedExpressionsEnum) == 11
        and len(NumberTypeEnum) == 2
    ), (
        "If you have added a new question/number type or managed expression, update this test to include the "
        "new question/number type or managed expression in `questions_to_test`."
    )

    new_grant_name = f"E2E developer_grant {grant_name_uuid}"
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # Set up new grant
    grant_dashboard_page = create_grant(new_grant_name, grant_name_uuid, all_grants_page)

    # Extract grant_id from URL (e.g., /deliver/grant/<uuid>/...)
    grant_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")

    # Go to Reports tab
    grant_reports_page = grant_dashboard_page.click_reports(new_grant_name)

    # Add a new report
    add_report_page = grant_reports_page.click_add_report()
    new_report_name = f"E2E report {uuid.uuid4()}"
    add_report_page.fill_in_report_name(new_report_name)
    grant_reports_page = add_report_page.click_submit(new_grant_name)
    grant_reports_page.check_report_exists(new_report_name)

    # Add a first task and a questions/question group
    add_section_page = grant_reports_page.click_add_section(report_name=new_report_name, grant_name=new_grant_name)

    # Extract collection_id from URL (e.g., /grant/<uuid>/reports/<uuid>/sections)
    collection_id = extract_uuid_from_url(page.url, r"/report/(?P<uuid>[a-f0-9-]+)")

    first_section_name = "E2E first task - grouped questions"
    add_section_page.fill_in_section_name(first_section_name)
    report_sections_page = add_section_page.click_add_section()
    report_sections_page.check_section_exists(first_section_name)

    manage_section_page = report_sections_page.click_manage_section(section_name=first_section_name)
    for question_to_test in section_1_questions_with_groups_to_test.values():
        create_question_or_group(question_to_test, manage_section_page)

    # Add a second task and a question of each type to the task
    report_sections_page = navigate_to_report_sections_page(page, domain, new_grant_name, new_report_name)
    add_section_page = report_sections_page.click_add_section()
    second_section_name = "E2E second task - all question types"
    add_section_page.fill_in_section_name(second_section_name)
    report_sections_page = add_section_page.click_add_section()
    report_sections_page.check_section_exists(second_section_name)

    manage_section_page = report_sections_page.click_manage_section(section_name=second_section_name)
    for question_to_test in section_2_questions_to_test.values():
        create_question_or_group(question_to_test, manage_section_page)

    # Add grant team member
    grant_team_page = manage_section_page.click_nav_grant_team()
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    add_grant_team_member_page.fill_in_user_email(grant_team_email)
    grant_team_page = add_grant_team_member_page.click_continue()

    # Switch to grant team member (claim invitation/userrole), then switch back to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    # Set up test organisation via admin for test grant recipient journey
    test_org_name = f"E2E Test Org {grant_name_uuid[:8]}"
    test_org_external_id = f"E2E-TEST-{grant_name_uuid[:8].upper()}"
    tsv_data = (
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"{test_org_external_id}\t{test_org_name}\tCentral Government\t\t\n"
    )

    reporting_lifecycle_tasklist_page = AdminReportingLifecycleTasklistPage(page, domain, grant_id, collection_id)
    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set up test grant recipients")
    set_up_grant_recipients_page = SetUpTestGrantRecipientsPage(page, domain, grant_id, collection_id)
    set_up_grant_recipients_page.select_organisation(test_org_name)
    set_up_grant_recipients_page.click_set_up_grant_recipients()

    reporting_lifecycle_tasklist_page.click_task("Set up test grant recipient users")
    set_up_users_page = SetUpTestGrantRecipientUsersPage(page, domain, grant_id, collection_id)
    set_up_users_page.select_test_grant_recipient(test_org_name)
    set_up_users_page.select_grant_team_member(grant_team_email)
    set_up_users_page.click_add_user()

    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set up organisations")

    # TODO make a new organisation and then remove at the end
    org_name = "MHCLG Funding Service Test Organisation"
    user_name = "MHCLG Test User"
    user_email = "fsd-post-award@levellingup.gov.uk"
    tsv_data = (
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"MHCLG-TEST-ORG\t{org_name}\tCentral Government\t\t\n"
    )
    set_up_orgs_page = SetUpOrganisationsPage(page, domain, grant_id, collection_id)
    set_up_orgs_page.fill_organisations_tsv_data(tsv_data)
    set_up_orgs_page.click_set_up_organisations()

    reporting_lifecycle_tasklist_page.click_task("Set up grant recipients")
    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, grant_id, collection_id)
    set_up_grant_recipients_page.select_organisation(org_name)
    set_up_grant_recipients_page.click_set_up_grant_recipients()

    tsv_data = f"organisation-name\tfull-name\temail-address\n{org_name}\t{user_name}\t{user_email}\n"
    reporting_lifecycle_tasklist_page.click_task("Set up grant recipient data providers")
    setup_data_providers_page = SetUpDataProvidersPage(page, domain, grant_id, collection_id)
    setup_data_providers_page.fill_users_tsv_data(tsv_data)
    setup_data_providers_page.click_set_up_users()

    reporting_lifecycle_tasklist_page.click_task("Override certifiers for this grant")
    override_certifiers_page = OverrideGrantRecipientCertifiersPage(page, domain, grant_id, collection_id)
    override_certifiers_page.select_organisation(org_name)
    override_certifiers_page.complete_user_details(user_name, user_email)
    override_certifiers_page.click_add_certifier()

    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set reporting dates")
    set_reporting_dates_page = SetReportingDatesPage(page, domain, grant_id, collection_id)
    set_reporting_dates_page.set_dates_for_open_report()
    set_reporting_dates_page.click_save_dates(report_name=new_report_name)

    reporting_lifecycle_tasklist_page.click_task("Mark as onboarding with Funding Service")
    mark_as_onboarding_page = MarkAsOnboardingWithFundingServicePage(page, domain, grant_id, collection_id)
    mark_as_onboarding_page.click_mark_as_onboarding()

    reporting_lifecycle_tasklist_page.click_task("Set privacy policy")
    set_privacy_policy_page = SetPrivacyPolicyPage(page, domain, grant_id, collection_id)
    set_privacy_policy_page.fill_privacy_policy_markdown("https://www.gov.uk/help/privacy-notice")
    set_privacy_policy_page.click_save_privacy_policy()

    # Do this the admin way so we don't have to create grant team users (that's why the option is
    # greyed out in the tasklist at this point)
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status("LIVE")
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status("OPEN")
    report_settings_page.click_save()

    # The report is now open and ready for submissions
    # TODO go on to login with the fsd-post-award user via magic link and complete the report

    # Store data for dependent tests
    _shared_setup_data = {
        "grant_name": new_grant_name,
        "grant_name_uuid": grant_name_uuid,
        "grant_id": grant_id,
        "collection_name": new_report_name,
        "collection_id": collection_id,
        "grant_team_email": grant_team_email,
        "first_section_name": first_section_name,
        "second_section_name": second_section_name,
        "test_org_name": test_org_name,
        "test_org_external_id": test_org_external_id,
        "grant_recipient_org": org_name,
        "grant_recipient_user_name": user_name,
        "grant_recipient_user_email": user_email,
    }


def test_preview_collection(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Grant team member previews and fills the collection."""
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    # Switch to grant team member
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, data["grant_team_email"])

    # Preview the report
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # This page can auto-redirect to the grant page; if it doesn't we should click the grant name.
    if all_grants_page.title.is_visible():
        all_grants_page.click_grant(data["grant_name"])

    grant_details_page = GrantDetailsPage(page, domain, data["grant_name"])
    grant_reports_page = grant_details_page.click_reports(data["grant_name"])
    report_sections_page = grant_reports_page.click_manage_sections(
        grant_name=data["grant_name"], report_name=data["collection_name"]
    )
    tasklist_page = report_sections_page.click_preview_report()

    # Check the tasklist has loaded
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_disabled()
    expect(tasklist_page.page.get_by_role("link", name=data["first_section_name"])).to_be_visible()
    # Second section is "Cannot start yet" state, so link should not be visible
    expect(tasklist_page.page.locator(".govuk-task-list__status", has_text="Cannot start yet")).to_be_visible()
    expect(tasklist_page.page.get_by_role("link", name=data["second_section_name"])).not_to_be_visible()

    # Complete the first task with question groups
    complete_task(
        tasklist_page, data["first_section_name"], data["grant_name"], section_1_questions_with_groups_to_test
    )

    # Check your answers page
    task_check_your_answers(
        tasklist_page, data["grant_name"], data["collection_name"], section_1_questions_with_groups_to_test
    )

    # Section two can be started now that section one is complete (because section two references data in section one).
    expect(tasklist_page.page.locator(".govuk-task-list__status", has_text="Cannot start yet")).not_to_be_visible()
    expect(tasklist_page.page.get_by_role("link", name=data["second_section_name"])).to_be_visible()

    # Complete the second task with flat questions list
    complete_task(tasklist_page, data["second_section_name"], data["grant_name"], section_2_questions_to_test)

    # Check your answers page
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], section_2_questions_to_test)

    # Submit the report
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()

    tasklist_page.click_submit_for_preview()


def test_deliver_test_grant_recipient_journey(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Grant team member triggers test submission via test organisation."""
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    # Switch to grant team member
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, data["grant_team_email"])

    test_journey_page = DeliverTestGrantRecipientJourneyPage(
        page, domain, data["grant_id"], data["collection_id"], data["collection_name"]
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(data["test_org_name"])
    test_journey_page.click_start_test_journey()

    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(data["test_org_name"], data["grant_name"])
    access_grant.click_collection(data["collection_name"])

    # We should now be on the tasklist page for the submission
    tasklist_page = RunnerTasklistPage(page, domain, data["grant_name"], data["collection_name"])

    # Check the tasklist has loaded
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.page.get_by_role("link", name=data["first_section_name"])).to_be_visible()
    # Second section is "Cannot start yet" state, so link should not be visible
    expect(tasklist_page.page.locator(".govuk-task-list__status", has_text="Cannot start yet")).to_be_visible()
    expect(tasklist_page.page.get_by_role("link", name=data["second_section_name"])).not_to_be_visible()

    # Complete the first task with question groups
    complete_task(
        tasklist_page, data["first_section_name"], data["grant_name"], section_1_questions_with_groups_to_test
    )

    # Check your answers page
    task_check_your_answers(
        tasklist_page, data["grant_name"], data["collection_name"], section_1_questions_with_groups_to_test
    )

    # Section two can be started now that section one is complete (because section two references data in section one).
    expect(tasklist_page.page.locator(".govuk-task-list__status", has_text="Cannot start yet")).not_to_be_visible()
    expect(tasklist_page.page.get_by_role("link", name=data["second_section_name"])).to_be_visible()

    # Complete the second task with flat questions list
    complete_task(tasklist_page, data["second_section_name"], data["grant_name"], section_2_questions_to_test)

    # Check your answers page
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], section_2_questions_to_test)

    # Submit the report
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()

    tasklist_page.click_submit_for_certify()

    # TODO - certify it?

    grant_reports_page = GrantReportsPage(page, domain, data["grant_name"])
    grant_reports_page.navigate(data["grant_id"])
    submissions_list_page = grant_reports_page.click_view_submissions(data["collection_name"])
    view_submission_page = submissions_list_page.click_on_submission(data["test_org_name"])
    view_submission_page.click_reset_submission()


def test_zzz_cleanup_grant(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Cleanup: delete the grant via admin panel. Named zzz_ to run last alphabetically."""
    if _shared_setup_data is None:
        pytest.skip("No setup data to clean up")

    # Switch to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    # Tidy up by deleting the grant via admin panel, which will cascade to all related entities
    delete_grant_recipient_through_admin(
        page, domain, _shared_setup_data["grant_name_uuid"], expected_grant_recipients_matching_search=2
    )
    delete_test_org_through_admin(page, domain, _shared_setup_data["test_org_external_id"])
    delete_grant_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
