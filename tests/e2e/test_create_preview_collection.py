import csv
import dataclasses
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
    GreaterThan,
    IsNo,
    IsYes,
    LessThan,
    ManagedExpression,
    Specifically,
)
from app.common.filters import format_thousands
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser, GuidanceText
from tests.e2e.pages import AllGrantsPage, GrantDashboardPage
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


@dataclasses.dataclass
class Condition:
    referenced_question: str
    managed_expression: ManagedExpression


class QuestionDict(TypedDict):
    type: QuestionDataType
    text: str  # this is mutated by the test runner to store the unique (uuid'd) question name
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
    "prefix-integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter the total cost as a number",
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
        "choices": ["option 1", "option 2", "option 3"],
        "answers": [
            _QuestionResponse("option 2"),
        ],
        "condition": Condition(referenced_question="Yes or no", managed_expression=IsYes(question_id=uuid.uuid4())),
    },
    "autocomplete": {
        "type": QuestionDataType.RADIOS,
        "text": "Select an option from the accessible autocomplete",
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
        "answers": [
            _QuestionResponse("E2E question text multi line\nwith a second line that's over the word limit"),
            _QuestionResponse("E2E question text multi line\nwith a second line"),
        ],
        "options": QuestionPresentationOptions(word_limit=10, rows=MultilineTextInputRows.LARGE),
    },
    "url": {
        "type": QuestionDataType.URL,
        "text": "Enter a website address",
        "answers": [
            _QuestionResponse("not-a-url", "Enter a website address in the correct format, like www.gov.uk"),
            _QuestionResponse("https://gov.uk"),
        ],
    },
    "text-single-line-not-shown": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "This question should not be shown",
        "answers": [_QuestionResponse("This question shouldn't be shown")],
        "condition": Condition(referenced_question="Yes or no", managed_expression=IsNo(question_id=uuid.uuid4())),
    },
}

questions_with_groups_to_test: dict[str, TQuestionToTest] = {
    "yes-no": {
        "type": QuestionDataType.YES_NO,
        "text": "Do you want to show question groups?",
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
                "answers": [_QuestionResponse("E2E question text single line")],
            },
            {
                "type": QuestionDataType.URL,
                "text": "Group Enter a website address",
                "answers": [
                    _QuestionResponse("https://gov.uk"),
                ],
            },
            {
                "type": QuestionDataType.EMAIL,
                "text": "Group Enter an email address",
                "answers": [
                    _QuestionResponse("group@example.com"),
                ],
            },
        ],
    },
    "text-single-line": {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "Enter another single line of text",
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
                "answers": [_QuestionResponse("E2E question text single line group")],
            },
            {
                "type": QuestionDataType.EMAIL,
                "text": "Second group Enter an email address",
                "answers": [
                    _QuestionResponse("group2@example.com"),
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


def create_question_or_group(question_definition: TQuestionToTest, manage_task_page: ManageTaskPage):
    if question_definition["type"] == "group":
        add_question_group_page = manage_task_page.click_add_question_group(question_definition["text"])
        add_question_group_page.fill_in_question_group_name()
        group_display_options_page = add_question_group_page.click_continue()
        group_display_options_page.click_question_group_display_type(question_definition["display_options"])
        edit_question_group_page = group_display_options_page.click_submit()
        if (
            question_definition.get("guidance") is not None
            and question_definition.get("display_options") == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        ):
            add_question_guidance(question_definition, edit_question_group_page)
        if question_definition.get("condition") is not None:
            add_condition(edit_question_group_page, question_definition["text"], question_definition["condition"])
        for question in question_definition["questions"]:
            create_question(question, edit_question_group_page)
        manage_task_page = edit_question_group_page.click_task_breadcrumb()
    else:
        create_question(question_definition, manage_task_page)


def create_question(question_definition: TQuestionToTest, manage_page: ManageTaskPage | EditQuestionGroupPage) -> None:
    question_type_page = manage_page.click_add_question()
    question_type_page.click_question_type(question_definition["type"])
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_definition["type"].value, exact=True)).to_be_visible()
    question_uuid = uuid.uuid4()
    question_text = f"{question_definition['text']} - {question_uuid}"
    question_definition["text"] = question_text
    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(f"e2e_question_{question_uuid}")
    question_details_page.fill_question_hint(f"e2e_hint_{question_uuid}")

    if question_definition["type"] in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
        question_details_page.fill_data_source_items(question_definition["choices"])

        options = question_definition.get("options")
        if options is not None and options.last_data_source_item_is_distinct_from_others is not None:
            question_details_page.click_other_option_checkbox()
            question_details_page.enter_other_option_text()

    if (
        question_definition["type"] in [QuestionDataType.INTEGER, QuestionDataType.TEXT_MULTI_LINE]
        and question_definition.get("options") is not None
    ):
        add_advanced_formatting(question_definition, question_details_page)

    edit_question_page = question_details_page.click_submit()

    if question_definition.get("guidance") is not None:
        add_question_guidance(question_definition, edit_question_page)
    if question_definition.get("validation") is not None:
        add_validation(edit_question_page, question_definition["text"], question_definition["validation"])
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
        case _:
            pass  # No advanced formatting for other question types


def add_question_guidance(
    question_definition: TQuestionToTest, edit_question_page: EditQuestionPage | EditQuestionGroupPage
) -> None:
    guidance = question_definition.get("guidance")
    if guidance is not None:
        add_guidance_page = edit_question_page.click_add_guidance()
        add_guidance_page.fill_guidance_heading(guidance.heading)
        add_guidance_page.fill_guidance_default()
        edit_question_page = add_guidance_page.click_save_guidance_button(edit_question_page)
        expect(edit_question_page.page.get_by_text("Page heading", exact=True)).to_be_visible()
        expect(edit_question_page.page.get_by_text("Guidance text", exact=True)).to_be_visible()
        edit_question_page.click_change_guidance()
        add_guidance_page.fill_guidance(guidance)
        add_guidance_page.click_save_guidance_button(edit_question_page)


def add_validation(edit_question_page: EditQuestionPage, question_text: str, validation: ManagedExpression) -> None:
    add_validation_page = edit_question_page.click_add_validation()
    add_validation_page.configure_managed_validation(validation)
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
    question_to_test: TQuestionToTest,
):
    if question_to_test.get("guidance") is not None:
        assert_question_visibility(question_page, question_to_test)
    for nested_question in question_to_test["questions"]:
        if question_to_test.get("guidance") is None:
            question_page = RunnerQuestionPage(
                tasklist_page.page, tasklist_page.domain, grant_name, nested_question["text"]
            )
            assert_question_visibility(question_page, nested_question)
        for question_response in nested_question["answers"]:
            question_page.respond_to_question(
                question_type=nested_question["type"],
                question_text=nested_question["text"],
                answer=question_response.answer,
            )
        if question_to_test["display_options"] == GroupDisplayOptions.ONE_QUESTION_PER_PAGE:
            question_page.click_continue()
    if question_to_test["display_options"] == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE:
        question_page.click_continue()


def complete_task(
    tasklist_page: RunnerTasklistPage, task_name: str, grant_name: str, questions_to_test: dict[str, TQuestionToTest]
) -> RunnerTasklistPage:
    tasklist_page.click_on_task(task_name=task_name)
    for question_to_test in questions_to_test.values():
        question_page = RunnerQuestionPage(
            tasklist_page.page, tasklist_page.domain, grant_name, question_to_test["text"]
        )

        if question_to_test["type"] == "group":
            complete_question_group(question_page, tasklist_page, grant_name, question_to_test)
        else:
            assert_question_visibility(question_page, question_to_test)
            for question_response in question_to_test["answers"]:
                if "This question should not be shown" not in question_to_test["text"]:
                    question_page.respond_to_question(
                        question_type=question_to_test["type"],
                        question_text=question_to_test["text"],
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

    for question_to_test in questions_to_test.values():
        if question_to_test["type"] == "group":
            for nested_question in question_to_test["questions"]:
                assert_check_your_answers(check_your_answers_page, nested_question)
        else:
            assert_check_your_answers(check_your_answers_page, question_to_test)

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

    question_heading = check_your_answers_page.page.get_by_text(question["text"], exact=True)
    expect(question_heading).to_be_visible()

    if question["type"] == QuestionDataType.CHECKBOXES:
        checkbox_answers_list = check_your_answers_page.page.get_by_test_id(f"answer-{question['text']}").locator("li")
        expect(checkbox_answers_list).to_have_text(question["answers"][-1].answer)
    elif question["type"] == QuestionDataType.INTEGER:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question['text']}")).to_have_text(
            f"{question['options'].prefix or ''}"
            f"{format_thousands(int(question['answers'][-1].answer))}"
            f"{question['options'].suffix or ''}"
        )
    else:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question['text']}")).to_have_text(
            question["answers"][-1].answer
        )


def assert_view_report_answers(answers_list: Locator, question: TQuestionToTest) -> None:
    if "This question should not be shown" in question["text"]:
        return
    if question["type"] == QuestionDataType.CHECKBOXES:
        expect(
            answers_list.get_by_text(f"{question['text']} {' '.join(question['answers'][-1].answer)}")
        ).to_be_visible()
    elif question["type"] == QuestionDataType.INTEGER:
        expect(
            answers_list.get_by_text(
                f"{question['text']} {question['options'].prefix or ''}"
                f"{format_thousands(int(question['answers'][-1].answer))}{question['options'].suffix or ''}"
            )
        ).to_be_visible()
    else:
        expect(answers_list.get_by_text(f"{question['text']} {question['answers'][-1].answer}")).to_be_visible()


@pytest.mark.skip_in_environments(["prod"])
def test_create_and_preview_report(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser
) -> None:
    try:
        # Sense check that the test includes all question types
        new_question_type_error = None
        try:
            assert len(QuestionDataType) == 8 and len(questions_to_test) == 12 and len(ManagedExpressionsEnum) == 7, (
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
        first_task_name = f"E2E question group task {uuid.uuid4()}"
        add_task_page.fill_in_task_name(first_task_name)
        report_tasks_page = add_task_page.click_add_task()
        report_tasks_page.check_task_exists(first_task_name)

        manage_task_page = report_tasks_page.click_manage_task(task_name=first_task_name)
        for question_to_test in questions_with_groups_to_test.values():
            create_question_or_group(question_to_test, manage_task_page)

        # Add a second task and a question of each type to the task
        report_tasks_page = navigate_to_report_tasks_page(page, domain, new_grant_name, new_report_name)
        add_task_page = report_tasks_page.click_add_task()
        second_task_name = f"E2E task {uuid.uuid4()}"
        add_task_page.fill_in_task_name(second_task_name)
        report_tasks_page = add_task_page.click_add_task()
        report_tasks_page.check_task_exists(second_task_name)

        manage_task_page = report_tasks_page.click_manage_task(task_name=second_task_name)
        for question_to_test in questions_to_test.values():
            create_question_or_group(question_to_test, manage_task_page)

        # Preview the report
        report_tasks_page = navigate_to_report_tasks_page(page, domain, new_grant_name, new_report_name)
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
        for question in questions_with_groups_to_test.values():
            if question["type"] == "group":
                for nested_question in question["questions"]:
                    assert_view_report_answers(answers_list, nested_question)
            else:
                assert_view_report_answers(answers_list, question)

        answers_list = view_submission_page.get_questions_list_for_task(second_task_name)
        expect(answers_list).to_be_visible()
        for question in questions_to_test.values():
            assert_view_report_answers(answers_list, question)

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
        # Tidy up by deleting the grant, which will cascade to all related entities
        all_grants_page.navigate()
        grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
        developers_page = grant_dashboard_page.click_developers(new_grant_name)
        developers_page.delete_grant()
        if new_question_type_error:
            raise new_question_type_error
