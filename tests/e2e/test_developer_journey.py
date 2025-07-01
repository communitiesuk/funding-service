import dataclasses
import uuid

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import QuestionDataType
from app.common.expressions.managed import GreaterThan, LessThan, ManagedExpression
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.developer_pages import CheckYourAnswersPage, CollectionDetailPage, ManageFormPage, QuestionPage
from tests.e2e.pages import AllGrantsPage


@dataclasses.dataclass
class _QuestionResponse:
    answer: str
    error_message: str | None = None


question_text_by_type: dict[QuestionDataType, str] = {
    QuestionDataType.TEXT_SINGLE_LINE: "Enter a single line of text",
    QuestionDataType.TEXT_MULTI_LINE: "Enter a few lines of text",
    QuestionDataType.INTEGER: "Enter a number",
}


question_response_data_by_type: dict[QuestionDataType, list[_QuestionResponse]] = {
    QuestionDataType.TEXT_SINGLE_LINE: [_QuestionResponse("E2E question text single line")],
    QuestionDataType.TEXT_MULTI_LINE: [_QuestionResponse("E2E question text multi line\nwith a second line")],
    QuestionDataType.INTEGER: [
        _QuestionResponse("0", "The answer must be greater than 1"),
        _QuestionResponse("101", "The answer must be less than or equal to 100"),
        _QuestionResponse("100"),
    ],
}

created_questions_to_test = []


def create_question(
    question_type: QuestionDataType,
    manage_form_page: ManageFormPage,
) -> None:
    question_type_page = manage_form_page.click_add_question()
    question_type_page.click_question_type(question_type.value)
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_type.value, exact=True)).to_be_visible()
    question_uuid = uuid.uuid4()
    question_text = f"{question_text_by_type[question_type]} - {question_uuid}"
    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(f"e2e_question_{question_uuid}")
    question_details_page.fill_question_hint(f"e2e_hint_{question_uuid}")
    manage_form_page = question_details_page.click_submit()
    manage_form_page.check_question_exists(question_text)

    created_questions_to_test.append(
        {"question_text": question_text, "question_responses": question_response_data_by_type[question_type]}
    )


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
    collection_detail_page = developers_page.click_on_collection(grant_name=grant_name, collection_name=collection_name)
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

        # Add a new section
        collection_detail_page = developers_page.click_on_collection(
            collection_name=new_collection_name, grant_name=new_grant_name
        )
        add_section_page = collection_detail_page.click_add_section()
        new_section_name = f"E2E section {uuid.uuid4()}"
        add_section_page.fill_in_section_title(new_section_name)
        sections_list_page = add_section_page.click_submit(collection_name=new_collection_name)
        sections_list_page.check_section_exists(new_section_name)

        # Add a new form
        section_detail_page = sections_list_page.click_manage_section(new_section_name)
        form_type_page = section_detail_page.click_add_form()
        form_type_page.click_add_empty_form()
        form_details_page = form_type_page.click_continue()
        form_name = f"E2E form {uuid.uuid4()}"
        form_details_page.fill_in_form_name(form_name)
        section_detail_page = form_details_page.click_add_form()
        section_detail_page.check_form_exists(form_name)

        # Add a question of each type
        manage_form_page = section_detail_page.click_manage_form(form_name)
        create_question(QuestionDataType.TEXT_SINGLE_LINE, manage_form_page)
        create_question(QuestionDataType.TEXT_MULTI_LINE, manage_form_page)
        create_question(QuestionDataType.INTEGER, manage_form_page)

        add_validation(
            manage_form_page,
            question_text_by_type[QuestionDataType.INTEGER],
            GreaterThan(question_id=uuid.uuid4(), minimum_value=1, inclusive=False),  # question_id does not matter here
        )

        add_validation(
            manage_form_page,
            question_text_by_type[QuestionDataType.INTEGER],
            LessThan(question_id=uuid.uuid4(), maximum_value=100, inclusive=True),  # question_id does not matter here
        )

        # Preview the form
        collection_detail_page = navigate_to_collection_detail_page(page, domain, new_grant_name, new_collection_name)
        tasklist_page = collection_detail_page.click_preview_collection()

        # Check the tasklist has loaded
        expect(tasklist_page.page.get_by_role("heading", name=new_section_name)).to_be_visible()
        expect(
            tasklist_page.collection_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_disabled()
        expect(tasklist_page.page.get_by_role("link", name=form_name)).to_be_visible()

        # Complete the first form
        tasklist_page.click_on_form(form_name=form_name)
        for question in created_questions_to_test:
            question_page = QuestionPage(page, domain, new_grant_name, question["question_text"])
            expect(question_page.heading).to_be_visible()

            for question_response in question["question_responses"]:
                question_page.respond_to_question(answer=question_response.answer)
                question_page.click_continue()

                if question_response.error_message:
                    expect(question_page.page.get_by_role("link", name=question_response.error_message)).to_be_visible()

        # Check the answers page
        check_your_answers = CheckYourAnswersPage(page, domain, new_grant_name)

        for question in created_questions_to_test:
            question_heading = check_your_answers.page.get_by_text(question["question_text"], exact=True)
            expect(question_heading).to_be_visible()
            expect(check_your_answers.page.get_by_test_id(f"answer-{question['question_text']}")).to_have_text(
                question["question_responses"][-1].answer
            )

        expect(check_your_answers.page.get_by_text("Have you completed this section?", exact=True)).to_be_visible()

        check_your_answers.click_mark_as_complete_yes()
        tasklist_page = check_your_answers.click_save_and_continue(collection_name=new_collection_name)

        # Submit the collection
        expect(
            tasklist_page.collection_status_box.filter(has=tasklist_page.page.get_by_text("In progress"))
        ).to_be_visible()
        expect(tasklist_page.submit_button).to_be_enabled()

        confirmation_page = tasklist_page.click_submit()
        collection_reference = confirmation_page.collection_reference.inner_text()

        # Go back to schema detail page
        collection_detail_page = navigate_to_collection_detail_page(page, domain, new_grant_name, new_collection_name)

        # View the collection
        expect(collection_detail_page.summary_row_submissions.get_by_text("1 test submission")).to_be_visible()
        collections_list_page = collection_detail_page.click_view_submissions()

        view_collection_page = collections_list_page.click_on_submission(collection_reference=collection_reference)

        answers_list = view_collection_page.get_questions_list_for_form(form_name)
        expect(answers_list).to_be_visible()
        for question in created_questions_to_test:
            expect(
                answers_list.get_by_text(f"{question['question_text']} {question['question_responses'][-1].answer}")
            ).to_be_visible()

    finally:
        # Tidy up by deleting the grant, which will cascade to all related entities
        all_grants_page.navigate()
        grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
        developers_page = grant_dashboard_page.click_developers(new_grant_name)
        developers_page.delete_grant()
