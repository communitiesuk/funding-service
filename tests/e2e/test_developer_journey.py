import dataclasses
import uuid
from typing import NotRequired, TypedDict

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import QuestionDataType, QuestionOptions
from app.common.expressions.managed import GreaterThan, LessThan, ManagedExpression
from app.constants import DEFAULT_SECTION_NAME
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.developer_pages import CheckYourAnswersPage, CollectionDetailPage, ManageFormPage, QuestionPage
from tests.e2e.pages import AllGrantsPage


@dataclasses.dataclass
class _QuestionResponse:
    answer: str
    error_message: str | None = None


TQuestionToTest = TypedDict(
    "TQuestionToTest",
    {
        "type": QuestionDataType,
        "text": str,  # this is mutated by the test runner to store the unique (uuid'd) question name
        "answers": list[_QuestionResponse],
        "choices": NotRequired[list[str]],
        "options": NotRequired[QuestionOptions],
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
    },
    "text-multi-line": {
        "type": QuestionDataType.TEXT_MULTI_LINE,
        "text": "Enter a few lines of text",
        "answers": [_QuestionResponse("E2E question text multi line\nwith a second line")],
    },
    "integer": {
        "type": QuestionDataType.INTEGER,
        "text": "Enter a number",
        "answers": [
            _QuestionResponse("0", "The answer must be greater than 1"),
            _QuestionResponse("101", "The answer must be less than or equal to 100"),
            _QuestionResponse("100"),
        ],
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
            _QuestionResponse("None of the above"),
        ],
        "options": QuestionOptions(last_data_source_item_is_distinct_from_others=True),
    },
    "url": {
        "type": QuestionDataType.URL,
        "text": "Enter a website address",
        "answers": [
            _QuestionResponse("not-a-url", "Enter a website address in the correct format, like www.gov.uk"),
            _QuestionResponse("https://gov.uk"),
        ],
    },
}


def create_question(
    question_definition: TQuestionToTest,
    manage_form_page: ManageFormPage,
) -> None:
    question_type_page = manage_form_page.click_add_question()
    question_type_page.click_question_type(question_definition["type"])
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_definition["type"].value, exact=True)).to_be_visible()
    question_uuid = uuid.uuid4()
    question_text = f"{question_definition['text']} - {question_uuid}"
    question_definition["text"] = question_text
    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(f"e2e_question_{question_uuid}")
    question_details_page.fill_question_hint(f"e2e_hint_{question_uuid}")

    if question_definition["type"] == QuestionDataType.RADIOS:
        question_details_page.fill_data_source_items(question_definition["choices"])

        options = question_definition.get("options")
        if options is not None and options.last_data_source_item_is_distinct_from_others is not None:
            question_details_page.click_fallback_option_checkbox()
            question_details_page.enter_fallback_option_text()

    question_details_page.click_submit()
    question_details_page.click_back()


def add_validation(manage_form_page: ManageFormPage, question_text: str, validation: ManagedExpression) -> None:
    edit_question_page = manage_form_page.click_edit_question(question_text)
    add_validation_page = edit_question_page.click_add_validation()
    add_validation_page.configure_managed_validation(validation)
    edit_question_page = add_validation_page.click_add_validation()
    edit_question_page.click_back()


def navigate_to_collection_detail_page(
    page: Page, domain: str, grant_name: str, collection_name: str
) -> CollectionDetailPage:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    developers_page = grant_dashboard_page.click_developers(grant_name)
    collection_detail_page = developers_page.click_manage_form(grant_name=grant_name, collection_name=collection_name)
    return collection_detail_page


@pytest.mark.skip_in_environments(["prod"])
def test_create_and_preview_collection(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser
):
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

        # Go to developers tab
        developers_page = grant_dashboard_page.click_developers(new_grant_name)

        # Add a new collection
        add_collection_page = developers_page.click_add_collection()
        new_collection_name = f"E2E collection {uuid.uuid4()}"
        add_collection_page.fill_in_collection_name(new_collection_name)
        developers_page = add_collection_page.click_submit(new_grant_name)
        developers_page.check_collection_exists(new_collection_name)

        collection_detail_page = developers_page.click_manage_form(
            collection_name=new_collection_name, grant_name=new_grant_name
        )

        # Add a new form
        form_type_page = collection_detail_page.click_add_form(DEFAULT_SECTION_NAME)
        form_type_page.click_add_empty_task()
        form_details_page = form_type_page.click_continue()
        form_name = f"E2E form {uuid.uuid4()}"
        form_details_page.fill_in_task_name(form_name)
        collection_detail_page = form_details_page.click_add_task()
        collection_detail_page.check_task_exists(DEFAULT_SECTION_NAME, form_name)

        # Add a question of each type
        manage_form_page = collection_detail_page.click_manage_form(
            section_title=DEFAULT_SECTION_NAME, form_name=form_name
        )
        for question_to_test in questions_to_test.values():
            create_question(question_to_test, manage_form_page)

        # TODO: move this into `question_to_test` definition as well
        add_validation(
            manage_form_page,
            questions_to_test["integer"]["text"],
            GreaterThan(question_id=uuid.uuid4(), minimum_value=1, inclusive=False),  # question_id does not matter here
        )

        add_validation(
            manage_form_page,
            questions_to_test["integer"]["text"],
            LessThan(question_id=uuid.uuid4(), maximum_value=100, inclusive=True),  # question_id does not matter here
        )

        # Preview the form
        collection_detail_page = navigate_to_collection_detail_page(page, domain, new_grant_name, new_collection_name)
        tasklist_page = collection_detail_page.click_test_form()

        # Check the tasklist has loaded
        expect(
            tasklist_page.collection_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_disabled()
        expect(tasklist_page.page.get_by_role("link", name=form_name)).to_be_visible()

        # Complete the first form
        tasklist_page.click_on_form(form_name=form_name)
        for question_to_test in questions_to_test.values():
            question_page = QuestionPage(page, domain, new_grant_name, question_to_test["text"])
            expect(question_page.heading).to_be_visible()

            for question_response in question_to_test["answers"]:
                question_page.respond_to_question(
                    question_type=question_to_test["type"], answer=question_response.answer
                )
                question_page.click_continue()

                if question_response.error_message:
                    expect(question_page.page.get_by_role("link", name=question_response.error_message)).to_be_visible()

        # Check the answers page
        check_your_answers = CheckYourAnswersPage(page, domain, new_grant_name)

        for question in questions_to_test.values():
            question_heading = check_your_answers.page.get_by_text(question["text"], exact=True)
            expect(question_heading).to_be_visible()
            expect(check_your_answers.page.get_by_test_id(f"answer-{question['text']}")).to_have_text(
                question["answers"][-1].answer
            )

        expect(check_your_answers.page.get_by_text("Have you completed this task?", exact=True)).to_be_visible()

        check_your_answers.click_mark_as_complete_yes()
        tasklist_page = check_your_answers.click_save_and_continue(collection_name=new_collection_name)

        # Submit the collection
        expect(
            tasklist_page.collection_status_box.filter(has=tasklist_page.page.get_by_text("In progress"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_enabled()

        collection_detail_page = tasklist_page.click_submit()

        # View the collection
        grant_details_page = collection_detail_page.click_back()
        expect(grant_details_page.summary_row_submissions.get_by_text("1 test submission")).to_be_visible()
        collections_list_page = grant_details_page.click_view_submissions(new_collection_name)

        view_collection_page = collections_list_page.click_on_first_submission()

        answers_list = view_collection_page.get_questions_list_for_form(form_name)
        expect(answers_list).to_be_visible()
        for question in questions_to_test.values():
            expect(answers_list.get_by_text(f"{question['text']} {question['answers'][-1].answer}")).to_be_visible()

    finally:
        # Tidy up by deleting the grant, which will cascade to all related entities
        all_grants_page.navigate()
        grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
        developers_page = grant_dashboard_page.click_developers(new_grant_name)
        developers_page.delete_grant()
