import csv
import dataclasses
import datetime
import json
import uuid
from typing import Literal, NotRequired, TypedDict, Union

import pytest
from playwright.sync_api import Locator, Page, expect

from app.common.data.types import (
    GroupDisplayOptions,
    ManagedExpressionsEnum,
    MultilineTextInputRows,
    NumberInputWidths,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions.managed import (
    AnyOf,
    Between,
    BetweenDates,
    GreaterThan,
    IsNo,
    IsYes,
    LessThan,
    ManagedExpression,
    Specifically,
)
from app.common.filters import format_thousands
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import (
    DeliverGrantFundingUserType,
    e2e_user_configs,
    login_with_session_cookie,
    login_with_stub_sso,
)
from tests.e2e.dataclasses import E2ETestUser, GuidanceText
from tests.e2e.pages import AllGrantsPage, GrantDashboardPage, GrantDetailsPage
from tests.e2e.reports_pages import (
    AddQuestionDetailsPage,
    EditQuestionGroupPage,
    EditQuestionPage,
    ManageTaskPage,
    ReportTasksPage,
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
    RunnerTasklistPage,
)


@dataclasses.dataclass
class _QuestionResponse:
    answer: str | list[str]
    error_message: str | None = None
    check_your_answers_text: str | None = None


@dataclasses.dataclass
class Condition:
    referenced_question: str
    managed_expression: ManagedExpression


class QuestionDict(TypedDict):
    type: QuestionDataType
    text: str
    display_text: str
    answers: list[_QuestionResponse]
    choices: NotRequired[list[str]]
    options: NotRequired[QuestionPresentationOptions]
    guidance: NotRequired[GuidanceText]
    validation: NotRequired[ManagedExpression]
    condition: NotRequired[Condition]


class QuestionGroupDict(TypedDict):
    type: Literal["group"]
    text: str
    display_options: GroupDisplayOptions
    guidance: NotRequired[GuidanceText]
    condition: NotRequired[Condition]
    questions: list[QuestionDict]


TQuestionToTest = Union[QuestionDict, QuestionGroupDict]

questions_to_test: dict[str, TQuestionToTest] = {
    "date": QuestionDict(
        type=QuestionDataType.DATE,
        text="Enter a date",
        display_text="Enter a date",
        answers=[
            _QuestionResponse(
                ["2003", "2", "01"],
                "The answer must be between 1 January 2020 (inclusive) and 1 January 2025 (exclusive)",
            ),
            _QuestionResponse(answer=["2022", "04", "05"], check_your_answers_text="5 April 2022"),
        ],
        validation=BetweenDates(
            question_id=uuid.uuid4(),
            earliest_value=datetime.date(2020, 1, 1),
            earliest_inclusive=True,
            latest_value=datetime.date(2025, 1, 1),
            latest_inclusive=False,
        ),
    ),
    "approx_date": QuestionDict(
        type=QuestionDataType.DATE,
        text="Enter an approximate date; your exact date was ((enter a date))",
        display_text="Enter an approximate date; your exact date was Tuesday 5 April 2022",
        answers=[
            _QuestionResponse(
                ["2003", "2"],
                "The answer must be between April 2020 (inclusive) and March 2022 (exclusive)",
            ),
            _QuestionResponse(["2021", "04"], check_your_answers_text="April 2021"),
        ],
        options=QuestionPresentationOptions(approximate_date=True),
        validation=BetweenDates(
            question_id=uuid.uuid4(),
            earliest_value=datetime.date(2020, 4, 1),
            earliest_inclusive=True,
            latest_value=datetime.date(2022, 3, 1),
            latest_inclusive=False,
        ),
    ),
    "prefix-integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter the total cost as a number",
        "display_text": "Enter the total cost as a number",
        "answers": [
            _QuestionResponse("0", "The answer must be greater than 1"),
            _QuestionResponse("10000"),
        ],
        "options": QuestionPresentationOptions(prefix="£", width=NumberInputWidths.BILLIONS),
        "validation": GreaterThan(
            question_id=uuid.uuid4(), minimum_value=1, inclusive=False
        ),  # question_id does not matter here
    },
    "suffix-integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter the total weight as a number",
        "display_text": "Enter the total weight as a number",
        "answers": [
            _QuestionResponse("101", "The answer must be less than or equal to 100"),
            _QuestionResponse("100"),
        ],
        "options": QuestionPresentationOptions(suffix="kg", width=NumberInputWidths.HUNDREDS),
        "validation": LessThan(
            question_id=uuid.uuid4(), maximum_value=100, inclusive=True
        ),  # question_id does not matter here
        "condition": Condition(
            referenced_question="Enter the total cost as a number",
            managed_expression=GreaterThan(question_id=uuid.uuid4(), minimum_value=1, inclusive=False),
        ),
    },
    "between-integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter a number between 20 and 100",
        "display_text": "Enter a number between 20 and 100",
        "answers": [
            _QuestionResponse("101", "The answer must be between 20 (inclusive) and 100 (exclusive)"),
            _QuestionResponse("20"),
        ],
        "options": QuestionPresentationOptions(),
        "validation": Between(
            question_id=uuid.uuid4(),
            maximum_value=100,
            maximum_inclusive=False,
            minimum_value=20,
            minimum_inclusive=True,
        ),  # question_id does not matter here
        "condition": Condition(
            referenced_question="Enter the total weight as a number",
            managed_expression=LessThan(question_id=uuid.uuid4(), maximum_value=100, inclusive=True),
        ),
    },
    "yes-no": {
        "type": QuestionDataType.YES_NO,
        "text": "Yes or no",
        "display_text": "Yes or no",
        "answers": [
            _QuestionResponse("Yes"),
        ],
        "condition": Condition(
            referenced_question="Enter a number between 20 and 100",
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
            _QuestionResponse("option 2"),
        ],
        "condition": Condition(referenced_question="Yes or no", managed_expression=IsYes(question_id=uuid.uuid4())),
    },
    "autocomplete": {
        "type": QuestionDataType.RADIOS,
        "text": "Select an option from the accessible autocomplete",
        "display_text": "Select an option from the accessible autocomplete",
        "choices": [f"option {x}" for x in range(1, 30)],
        "answers": [
            _QuestionResponse("Other"),
        ],
        "options": QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        "condition": Condition(
            referenced_question="Select an option",
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
            _QuestionResponse(["option 2", "option 3"]),
        ],
        "options": QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        "condition": Condition(
            referenced_question="Select an option from the accessible autocomplete",
            managed_expression=AnyOf(question_id=uuid.uuid4(), items=[{"key": "other", "label": "Other"}]),
        ),
    },
    "email": {
        "type": QuestionDataType.EMAIL,
        "text": "Enter an email address",
        "display_text": "Enter an email address",
        "answers": [
            _QuestionResponse("not-an-email", "Enter an email address in the correct format, like name@example.com"),
            _QuestionResponse("name@example.com"),
        ],
        "condition": Condition(
            referenced_question="Select one or more options",
            managed_expression=Specifically(question_id=uuid.uuid4(), item={"key": "option-2", "label": "option 2"}),
        ),
    },
    "text-single-line": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "Enter a single line of text",
        "display_text": "Enter a single line of text",
        "answers": [_QuestionResponse("E2E question text single line")],
        "guidance": GuidanceText(
            heading="This is a guidance page heading",
            body_heading="Guidance subheading",
            body_link_text="Design system link text",
            body_link_url="https://design-system.service.gov.uk",
            body_ol_items=["UL item one", "UL item two"],
            body_ul_items=["OL item one", "OL item two"],
        ),
    },
    "text-multi-line": {
        "type": QuestionDataType.TEXT_MULTI_LINE,
        "text": "Enter a few lines of text",
        "display_text": "Enter a few lines of text",
        "answers": [
            _QuestionResponse("E2E question text multi line\nwith a second line that's over the word limit"),
            _QuestionResponse("E2E question text multi line\nwith a second line"),
        ],
        "options": QuestionPresentationOptions(word_limit=10, rows=MultilineTextInputRows.LARGE),
    },
    "url": {
        "type": QuestionDataType.URL,
        "text": "Enter a website address",
        "display_text": "Enter a website address",
        "answers": [
            _QuestionResponse("not-a-url", "Enter a website address in the correct format, like www.gov.uk"),
            _QuestionResponse("https://gov.uk"),
        ],
    },
    "text-single-line-not-shown": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "This question should not be shown",
        "display_text": "This question should not be shown",
        "answers": [_QuestionResponse("This question shouldn't be shown")],
        "condition": Condition(referenced_question="Yes or no", managed_expression=IsNo(question_id=uuid.uuid4())),
    },
}


TQuestionToTest = Union[QuestionDict, QuestionGroupDict]


questions_with_groups_to_test: dict[str, TQuestionToTest] = {
    "yes-no": {
        "type": QuestionDataType.YES_NO,
        "text": "Do you want to show question groups?",
        "display_text": "Do you want to show question groups?",
        "answers": [
            _QuestionResponse("Yes"),
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
            body_ol_items=["UL item one", "UL item two"],
            body_ul_items=["OL item one", "OL item two"],
        ),
        "condition": Condition(
            referenced_question="Do you want to show question groups?",
            managed_expression=IsYes(question_id=uuid.uuid4()),
        ),
        "questions": [
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "Group Enter a single line of text",
                "display_text": "Group Enter a single line of text",
                "answers": [_QuestionResponse("E2E question text single line")],
            },
            {
                "type": QuestionDataType.URL,
                "text": "Group Enter a website address",
                "display_text": "Group Enter a website address",
                "answers": [
                    _QuestionResponse("https://gov.uk"),
                ],
            },
            {
                "type": QuestionDataType.EMAIL,
                "text": "Group Enter an email address",
                "display_text": "Group Enter an email address",
                "answers": [
                    _QuestionResponse("group@example.com"),
                ],
            },
        ],
    },
    "text-single-line": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "Enter another single line of text",
        "display_text": "Enter another single line of text",
        "answers": [_QuestionResponse("E2E question text single line second answer")],
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
                "answers": [_QuestionResponse("E2E question text single line group")],
            },
            {
                "type": QuestionDataType.EMAIL,
                "text": "Second group Enter an email address",
                "display_text": "Second group Enter an email address",
                "answers": [
                    _QuestionResponse("group2@example.com"),
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
                        "answers": [_QuestionResponse("E2E question text single line nested group")],
                    },
                    {
                        "type": QuestionDataType.EMAIL,
                        "text": "Nested group Enter an email address",
                        "display_text": "Nested group Enter an email address",
                        "answers": [
                            _QuestionResponse("nested_group@example.com"),
                        ],
                    },
                ],
            },
        ],
    },
}


def create_grant(new_grant_name: str, all_grants_page: AllGrantsPage) -> GrantDashboardPage:
    grant_intro_page = all_grants_page.click_set_up_a_grant()
    grant_ggis_page = grant_intro_page.click_continue()
    grant_ggis_page.select_yes()
    grant_ggis_page.fill_ggis_number()
    grant_name_page = grant_ggis_page.click_save_and_continue()
    grant_name_page.fill_name(new_grant_name)
    grant_description_page = grant_name_page.click_save_and_continue()
    grant_description_page.fill_description()
    grant_contact_page = grant_description_page.click_save_and_continue()
    grant_contact_page.fill_contact_name()
    grant_contact_page.fill_contact_email()
    grant_check_your_answers_page = grant_contact_page.click_save_and_continue()
    grant_dashboard_page = grant_check_your_answers_page.click_add_grant()
    return grant_dashboard_page


def create_question_or_group(
    question_definition: TQuestionToTest,
    manage_task_page: ManageTaskPage | EditQuestionGroupPage,
    parent_group_name: str | None = None,
):
    if question_definition["type"] == "group":
        add_question_group_page = manage_task_page.click_add_question_group(question_definition["text"])
        add_question_group_page.fill_in_question_group_name()
        group_display_options_page = add_question_group_page.click_continue()
        group_display_options_page.click_question_group_display_type(question_definition["display_options"])
        edit_question_group_page = group_display_options_page.click_submit(parent_group_name)
        if (
            question_definition.get("guidance") is not None
            and question_definition.get("display_options") == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        ):
            add_question_guidance(question_definition, edit_question_group_page)
        if question_definition.get("condition") is not None:
            add_condition(edit_question_group_page, question_definition["text"], question_definition["condition"])
        for question in question_definition["questions"]:
            create_question_or_group(question, edit_question_group_page, parent_group_name=question_definition["text"])
        if parent_group_name:
            edit_question_group_page.click_parent_group_breadcrumb()
        else:
            edit_question_group_page.click_task_breadcrumb()
    else:
        create_question(question_definition, manage_task_page, parent_group_name=parent_group_name)


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
    manage_page: ManageTaskPage | EditQuestionGroupPage,
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

    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(question_text.lower())
    question_details_page.fill_question_hint(f"Hint text for: {question_text}")

    if question_definition["type"] in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
        question_details_page.fill_data_source_items(question_definition["choices"])

        options = question_definition.get("options")
        if options is not None and options.last_data_source_item_is_distinct_from_others is not None:
            question_details_page.click_other_option_checkbox()
            question_details_page.enter_other_option_text()

    if (
        question_definition["type"]
        in [QuestionDataType.INTEGER, QuestionDataType.TEXT_MULTI_LINE, QuestionDataType.DATE]
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
            question_definition["text"],
            question_definition["validation"],
            question_definition.get("options", None),
        )
    if question_definition.get("condition") is not None:
        add_condition(edit_question_page, question_definition["text"], question_definition["condition"])

    if isinstance(manage_page, EditQuestionGroupPage):
        edit_question_page.click_question_group_breadcrumb(manage_page.group_name)
    else:
        edit_question_page.click_task_breadcrumb()


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
        case QuestionDataType.INTEGER:
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
    question_text: str,
    validation: ManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    add_validation_page = edit_question_page.click_add_validation()
    add_validation_page.configure_managed_validation(validation, presentation_options)
    edit_question_page = add_validation_page.click_add_validation()


def add_condition(
    edit_question_page: EditQuestionPage | EditQuestionGroupPage, question_text: str, condition: Condition
) -> None:
    add_condition_page = edit_question_page.click_add_condition()
    add_condition_page.select_condition_question(condition.referenced_question)
    add_condition_page.configure_managed_condition(condition.managed_expression)
    edit_question_page = add_condition_page.click_add_condition(edit_question_page)


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
    tasklist_page: RunnerTasklistPage, task_name: str, grant_name: str, questions_to_test: dict[str, TQuestionToTest]
) -> RunnerTasklistPage:
    tasklist_page.click_on_task(task_name=task_name)
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

    expect(check_your_answers_page.page.get_by_text("Have you completed this task?", exact=True)).to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)


def navigate_to_report_tasks_page(page: Page, domain: str, grant_name: str, report_name: str) -> ReportTasksPage:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    report_tasks_page = grant_reports_page.click_manage_tasks(grant_name=grant_name, report_name=report_name)
    return report_tasks_page


def assert_question_visibility(question_page: RunnerQuestionPage, question_to_test: TQuestionToTest) -> None:
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
    elif question["type"] == QuestionDataType.INTEGER:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            f"{question['options'].prefix or ''}"
            f"{format_thousands(int(question['answers'][-1].answer))}"
            f"{question['options'].suffix or ''}"
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
    elif question["type"] == QuestionDataType.INTEGER:
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


@pytest.mark.skip_in_environments(["prod"])
def test_create_and_preview_report(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    try:
        # Sense check that the test includes all question types
        new_question_type_error = None
        try:
            assert len(QuestionDataType) == 9 and len(questions_to_test) == 14 and len(ManagedExpressionsEnum) == 10, (
                "If you have added a new question type or managed expression, update this test to include the "
                "new question type or managed expression in `questions_to_test`."
            )
        except AssertionError as e:
            new_question_type_error = e

        new_grant_name = f"E2E developer_grant {uuid.uuid4()}"
        all_grants_page = AllGrantsPage(page, domain)
        all_grants_page.navigate()

        # Set up new grant
        grant_dashboard_page = create_grant(new_grant_name, all_grants_page)

        # Go to Reports tab
        grant_reports_page = grant_dashboard_page.click_reports(new_grant_name)

        # Add a new report
        add_report_page = grant_reports_page.click_add_report()
        new_report_name = f"E2E report {uuid.uuid4()}"
        add_report_page.fill_in_report_name(new_report_name)
        grant_reports_page = add_report_page.click_submit(new_grant_name)
        grant_reports_page.check_report_exists(new_report_name)

        # Add a first task and a questions/question group
        add_task_page = grant_reports_page.click_add_task(report_name=new_report_name, grant_name=new_grant_name)
        first_task_name = "E2E first task - grouped questions"
        add_task_page.fill_in_task_name(first_task_name)
        report_tasks_page = add_task_page.click_add_task()
        report_tasks_page.check_task_exists(first_task_name)

        manage_task_page = report_tasks_page.click_manage_task(task_name=first_task_name)
        for question_to_test in questions_with_groups_to_test.values():
            create_question_or_group(question_to_test, manage_task_page)

        # Add a second task and a question of each type to the task
        report_tasks_page = navigate_to_report_tasks_page(page, domain, new_grant_name, new_report_name)
        add_task_page = report_tasks_page.click_add_task()
        second_task_name = "E2E second task - all question types"
        add_task_page.fill_in_task_name(second_task_name)
        report_tasks_page = add_task_page.click_add_task()
        report_tasks_page.check_task_exists(second_task_name)

        manage_task_page = report_tasks_page.click_manage_task(task_name=second_task_name)
        for question_to_test in questions_to_test.values():
            create_question_or_group(question_to_test, manage_task_page)

        # Add grant team member
        grant_team_page = manage_task_page.click_nav_grant_team()
        add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
        grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
        add_grant_team_member_page.fill_in_user_email(grant_team_email)
        grant_team_page = add_grant_team_member_page.click_continue()

        # Sign out and switch to grant team member
        switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)

        # Preview the report
        grant_details_page = GrantDetailsPage(page, domain, new_grant_name)
        grant_reports_page = grant_details_page.click_reports(new_grant_name)
        report_tasks_page = grant_reports_page.click_manage_tasks(
            grant_name=new_grant_name, report_name=new_report_name
        )
        tasklist_page = report_tasks_page.click_preview_report()

        # Check the tasklist has loaded
        expect(
            tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_disabled()
        expect(tasklist_page.page.get_by_role("link", name=first_task_name)).to_be_visible()
        expect(tasklist_page.page.get_by_role("link", name=second_task_name)).to_be_visible()

        # Complete the first task with question groups
        complete_task(tasklist_page, first_task_name, new_grant_name, questions_with_groups_to_test)

        # Check your answers page
        task_check_your_answers(tasklist_page, new_grant_name, new_report_name, questions_with_groups_to_test)

        # Complete the second task with flat questions list
        complete_task(tasklist_page, second_task_name, new_grant_name, questions_to_test)

        # Check your answers page
        task_check_your_answers(tasklist_page, new_grant_name, new_report_name, questions_to_test)

        # Submit the report
        expect(
            tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("In progress"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_enabled()

        report_tasks_page = tasklist_page.click_submit()

        # View the submitted report
        grant_reports_page = report_tasks_page.click_reports_breadcrumb()
        expect(grant_reports_page.summary_row_submissions.get_by_text("1 test submission")).to_be_visible()
        submissions_list_page = grant_reports_page.click_view_submissions(new_report_name)

        view_submission_page = submissions_list_page.click_on_first_submission()

        answers_list = view_submission_page.get_questions_list_for_task(first_task_name)
        expect(answers_list).to_be_visible()

        assert_check_your_answer_for_all_questions(list(questions_with_groups_to_test.values()), answers_list)

        answers_list = view_submission_page.get_questions_list_for_task(second_task_name)
        expect(answers_list).to_be_visible()
        assert_check_your_answer_for_all_questions(list(questions_to_test.values()), answers_list)

        submissions_list_page = view_submission_page.click_submissions_breadcrumb()

        # Download CSV
        csv_export_filename = submissions_list_page.click_export(filetype="CSV")
        assert csv_export_filename.endswith(".csv")
        with open(csv_export_filename, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 2  # Header + 1 submission

        # Download JSON
        json_export_filename = submissions_list_page.click_export(filetype="JSON")
        assert json_export_filename.endswith(".json")
        with open(json_export_filename, "r", encoding="utf-8") as f:
            export_data = json.load(f)
            assert isinstance(export_data["submissions"], list)
            assert len(export_data["submissions"]) == 1
            assert isinstance(export_data["submissions"][0], dict)

    finally:
        # Sign out and switch to platform admin
        switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

        # Tidy up by deleting the grant, which will cascade to all related entities
        all_grants_page.navigate()
        grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
        developers_page = grant_dashboard_page.click_developers(new_grant_name)
        developers_page.delete_grant()
        if new_question_type_error:
            raise new_question_type_error
