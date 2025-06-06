import uuid

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import QuestionDataType
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.developer_pages import CheckYourAnswersPage, ManageFormPage, QuestionPage
from tests.e2e.pages import AllGrantsPage

question_response_data_by_type = {
    QuestionDataType.TEXT_SINGLE_LINE.value: "E2E question text single line",
    QuestionDataType.TEXT_MULTI_LINE.value: "E2E question text multi line\nwith a second line",
    QuestionDataType.INTEGER.value: "234",
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
    question_text = f"E2E question {question_uuid}"
    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(f"e2e_question_{question_uuid}")
    question_details_page.fill_question_hint(f"e2e_hint_{question_uuid}")
    manage_form_page = question_details_page.click_submit()
    manage_form_page.check_question_exists(question_text)

    created_questions_to_test.append(
        {"question_text": question_text, "question_response": question_response_data_by_type[question_type.value]}
    )


@pytest.mark.skip_in_environments(["dev", "test", "prod"])
def test_create_and_preview_schema(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser
):
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
    grant_confirmation_page = grant_check_your_answers_page.click_add_grant()
    grant_dashboard_page = grant_confirmation_page.click_continue()

    # Go to developers tab
    developers_page = grant_dashboard_page.click_developers(new_grant_name)
    manage_schemas_page = developers_page.click_manage_schemas(grant_name=new_grant_name)

    # Add a new schema
    add_schema_page = manage_schemas_page.click_add_schema()
    new_schema_name = f"E2E schema {uuid.uuid4()}"
    add_schema_page.fill_in_schema_name(new_schema_name)
    manage_schemas_page = add_schema_page.click_submit(new_grant_name)
    manage_schemas_page.check_schema_exists(new_schema_name)

    # Add a new section
    schema_detail_page = manage_schemas_page.click_on_schema(schema_name=new_schema_name, grant_name=new_grant_name)
    add_section_page = schema_detail_page.click_add_section()
    new_section_name = f"E2E section {uuid.uuid4()}"
    add_section_page.fill_in_section_title(new_section_name)
    sections_list_page = add_section_page.click_submit(schema_name=new_schema_name)
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

    # Preview the form
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
    developers_page = grant_dashboard_page.click_developers(new_grant_name)
    list_schemas_page = developers_page.click_manage_schemas(grant_name=new_grant_name)
    schema_detail_page = list_schemas_page.click_on_schema(grant_name=new_grant_name, schema_name=new_schema_name)
    tasklist_page = schema_detail_page.click_preview_collection()

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
        question_page.respond_to_question(answer=question["question_response"])
        question_page.click_continue()

    # Check the answers page
    check_your_answers = CheckYourAnswersPage(page, domain, new_grant_name)

    for question in created_questions_to_test:
        question_heading = check_your_answers.page.get_by_text(question["question_text"], exact=True)
        expect(question_heading).to_be_visible()
        expect(check_your_answers.page.get_by_test_id(f"answer-{question['question_text']}")).to_have_text(
            question["question_response"]
        )

    expect(check_your_answers.page.get_by_text("Have you completed this section?", exact=True)).to_be_visible()

    check_your_answers.click_mark_as_complete_yes()
    tasklist_page = check_your_answers.click_save_and_continue(schema_name=new_schema_name)

    # Submit the collection
    expect(
        tasklist_page.collection_status_box.filter(has=tasklist_page.page.get_by_text("In progress"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()
    tasklist_page = tasklist_page.click_submit_collection()

    # Check the collection status is now completed
    expect(tasklist_page.collection_status_box.filter(has=tasklist_page.page.get_by_text("Completed"))).to_be_visible()
    expect(tasklist_page.submit_button).not_to_be_visible()
