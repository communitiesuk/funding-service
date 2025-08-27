import dataclasses
import uuid
from typing import NotRequired, TypedDict

import pytest
from playwright.sync_api import Locator, Page, expect

from app.common.data.types import (
    MultilineTextInputRows,
    NumberInputWidths,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions.managed import GreaterThan, LessThan, ManagedExpression
from app.common.filters import format_thousands
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser, GuidanceText
from tests.e2e.pages import AllGrantsPage
from tests.e2e.reports_pages import (
    AddQuestionDetailsPage,
    EditQuestionPage,
    ManageTaskPage,
    ReportTasksPage,
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
)


@dataclasses.dataclass
class _QuestionResponse:
    answer: str | list[str]
    error_message: str | None = None


TQuestionToTest = TypedDict(
    "TQuestionToTest",
    {
        "type": QuestionDataType,
        "text": str,  # this is mutated by the test runner to store the unique (uuid'd) question name
        "answers": list[_QuestionResponse],
        "choices": NotRequired[list[str]],
        "options": NotRequired[QuestionPresentationOptions],
        "guidance": NotRequired[GuidanceText],
    },
)


questions_to_test: dict[str, TQuestionToTest] = {
    "email": {
        "type": QuestionDataType.EMAIL,
        "text": "Enter an email address",
        "answers": [
            _QuestionResponse("not-an-email", "Enter an email address in the correct format, like name@example.com"),
            _QuestionResponse("name@example.com"),
        ],
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
    "prefix-integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter the total cost as a number",
        "answers": [
            _QuestionResponse("0", "The answer must be greater than 1"),
            _QuestionResponse("10000"),
        ],
        "options": QuestionPresentationOptions(prefix="£", width=NumberInputWidths.BILLIONS),
    },
    "suffix-integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter the total weight as a number",
        "answers": [
            _QuestionResponse("101", "The answer must be less than or equal to 100"),
            _QuestionResponse("100"),
        ],
        "options": QuestionPresentationOptions(suffix="kg", width=NumberInputWidths.HUNDREDS),
    },
    "yes-no": {
        "type": QuestionDataType.YES_NO,
        "text": "Yes or no",
        "answers": [
            _QuestionResponse("Yes"),
        ],
    },
    "radio": {
        "type": QuestionDataType.RADIOS,
        "text": "Select an option",
        "choices": ["option 1", "option 2", "option 3"],
        "answers": [
            _QuestionResponse("option 2"),
        ],
    },
    "autocomplete": {
        "type": QuestionDataType.RADIOS,
        "text": "Select an option from the accessible autocomplete",
        "choices": [f"option {x}" for x in range(1, 30)],
        "answers": [
            _QuestionResponse("Other"),
        ],
        "options": QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
    },
    "url": {
        "type": QuestionDataType.URL,
        "text": "Enter a website address",
        "answers": [
            _QuestionResponse("not-a-url", "Enter a website address in the correct format, like www.gov.uk"),
            _QuestionResponse("https://gov.uk"),
        ],
    },
    "checkboxes": {
        "type": QuestionDataType.CHECKBOXES,
        "text": "Select one or more options",
        "choices": ["option 1", "option 2", "option 3", "option 4"],
        "answers": [
            _QuestionResponse(["option 2", "option 3"]),
        ],
        "options": QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
    },
}


def create_question(question_definition: TQuestionToTest, manage_task_page: ManageTaskPage) -> None:
    question_type_page = manage_task_page.click_add_question()
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
        edit_question_page.click_save()
    else:
        edit_question_page.click_return_to_task()


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


def add_question_guidance(question_definition: TQuestionToTest, edit_question_page: EditQuestionPage) -> None:
    add_guidance_page = edit_question_page.click_add_guidance()
    guidance = question_definition.get("guidance")
    if guidance is not None:
        add_guidance_page.fill_guidance_heading(guidance.heading)
        add_guidance_page.fill_guidance_default()
        edit_question_page = add_guidance_page.click_save_guidance_button()
        expect(edit_question_page.page.get_by_text("Page heading", exact=True)).to_be_visible()
        expect(edit_question_page.page.get_by_text("Guidance text", exact=True)).to_be_visible()
        edit_question_page.click_change_guidance()
        add_guidance_page.fill_guidance(guidance)
        add_guidance_page.click_save_guidance_button()


def add_validation(manage_task_page: ManageTaskPage, question_text: str, validation: ManagedExpression) -> None:
    edit_question_page = manage_task_page.click_edit_question(question_text)
    add_validation_page = edit_question_page.click_add_validation()
    add_validation_page.configure_managed_validation(validation)
    edit_question_page = add_validation_page.click_add_validation()
    edit_question_page.click_task_breadcrumb()


def navigate_to_report_tasks_page(page: Page, domain: str, grant_name: str, report_name: str) -> ReportTasksPage:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    report_tasks_page = grant_reports_page.click_manage_tasks(grant_name=grant_name, report_name=report_name)
    return report_tasks_page


def assert_question_guidance_visibility(question_page: RunnerQuestionPage, question_to_test: TQuestionToTest) -> None:
    expect(question_page.page.get_by_role("heading", name=question_to_test["guidance"].heading)).to_be_visible()
    expect(question_page.page.get_by_role("heading", name=question_to_test["guidance"].body_heading)).to_be_visible()
    expect(question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)).to_be_visible()
    expect(question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)).to_have_attribute(
        "href", question_to_test["guidance"].body_link_url
    )
    for item in question_to_test["guidance"].body_ul_items:
        expect(question_page.page.locator("ul").get_by_text(item)).to_be_visible()
    for item in question_to_test["guidance"].body_ol_items:
        expect(question_page.page.locator("ol").get_by_text(item)).to_be_visible()


def assert_check_your_answers(check_your_answers_page: RunnerCheckYourAnswersPage, question: TQuestionToTest) -> None:
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
        new_grant_name = f"E2E developer_grant {uuid.uuid4()}"
        all_grants_page = AllGrantsPage(page, domain)
        all_grants_page.navigate()

        # Set up new grant
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

        # Go to Reports tab
        grant_reports_page = grant_dashboard_page.click_reports(new_grant_name)

        # Add a new report
        add_report_page = grant_reports_page.click_add_report()
        new_report_name = f"E2E report {uuid.uuid4()}"
        add_report_page.fill_in_report_name(new_report_name)
        grant_reports_page = add_report_page.click_submit(new_grant_name)
        grant_reports_page.check_report_exists(new_report_name)

        # Add a new task
        add_task_page = grant_reports_page.click_add_task(report_name=new_report_name, grant_name=new_grant_name)
        task_name = f"E2E task {uuid.uuid4()}"
        add_task_page.fill_in_task_name(task_name)
        report_tasks_page = add_task_page.click_add_task()
        report_tasks_page.check_task_exists(task_name)

        manage_task_page = report_tasks_page.click_manage_task(task_name=task_name)

        # Sense check that the test includes all question types
        new_question_type_error = None
        try:
            assert len(QuestionDataType) == 8 and len(questions_to_test) == 10, (
                "If you have added a new question type, please update this test to include the new type in "
                "`questions_to_test`."
            )
        except AssertionError as e:
            new_question_type_error = e

        # Add a question of each type
        for question_to_test in questions_to_test.values():
            create_question(question_to_test, manage_task_page)

        # TODO: move this into `question_to_test` definition as well
        add_validation(
            manage_task_page,
            questions_to_test["prefix-integer"]["text"],
            GreaterThan(question_id=uuid.uuid4(), minimum_value=1, inclusive=False),  # question_id does not matter here
        )

        add_validation(
            manage_task_page,
            questions_to_test["suffix-integer"]["text"],
            LessThan(question_id=uuid.uuid4(), maximum_value=100, inclusive=True),  # question_id does not matter here
        )

        # Preview the report
        report_tasks_page = navigate_to_report_tasks_page(page, domain, new_grant_name, new_report_name)
        tasklist_page = report_tasks_page.click_preview_report()

        # Check the tasklist has loaded
        expect(
            tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_disabled()
        expect(tasklist_page.page.get_by_role("link", name=task_name)).to_be_visible()

        # Complete the first task
        tasklist_page.click_on_task(task_name=task_name)
        for question_to_test in questions_to_test.values():
            question_page = RunnerQuestionPage(page, domain, new_grant_name, question_to_test["text"])
            if question_to_test.get("guidance") is None:
                expect(question_page.heading).to_be_visible()
            else:
                assert_question_guidance_visibility(question_page, question_to_test)

            for question_response in question_to_test["answers"]:
                question_page.respond_to_question(
                    question_type=question_to_test["type"], answer=question_response.answer
                )
                question_page.click_continue()

                if question_response.error_message:
                    expect(question_page.page.get_by_role("link", name=question_response.error_message)).to_be_visible()

        # Check the answers page
        check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, new_grant_name)

        for question in questions_to_test.values():
            question_heading = check_your_answers_page.page.get_by_text(question["text"], exact=True)
            expect(question_heading).to_be_visible()
            assert_check_your_answers(check_your_answers_page, question)

        expect(check_your_answers_page.page.get_by_text("Have you completed this task?", exact=True)).to_be_visible()

        check_your_answers_page.click_mark_as_complete_yes()
        tasklist_page = check_your_answers_page.click_save_and_continue(report_name=new_report_name)

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

        view_report_page = submissions_list_page.click_on_first_submission()

        answers_list = view_report_page.get_questions_list_for_task(task_name)
        expect(answers_list).to_be_visible()
        for question in questions_to_test.values():
            assert_view_report_answers(answers_list, question)

    finally:
        # Tidy up by deleting the grant, which will cascade to all related entities
        all_grants_page.navigate()
        grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
        developers_page = grant_dashboard_page.click_developers(new_grant_name)
        developers_page.delete_grant()
        if new_question_type_error:
            raise new_question_type_error
