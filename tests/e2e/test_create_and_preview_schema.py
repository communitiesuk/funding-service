import uuid

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import QuestionDataType
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.developer_pages import ManageFormPage
from tests.e2e.pages import AllGrantsPage, GrantDashboardPage


def create_grant(new_grant_name: str, page: Page, domain: str) -> GrantDashboardPage:
    """
    Split this out as a separate function for now while we decide if we want this test to create the grant it uses,
    or whether we go with a different option
    (See notes in ticket FSPT-441)
    :param new_grant_name: name of grant to create
    :param page: page object from Playwright
    :param domain: domain to use for the test
    :return: Grant dashboard page object for the newly created grant
    """
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
    return grant_dashboard_page


def create_question(
    question_type: str,
    manage_form_page: ManageFormPage,
) -> None:
    question_type_page = manage_form_page.click_add_question()
    question_type_page.click_question_type(question_type)
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_type, exact=True)).to_be_visible()
    question_uuid = uuid.uuid4()
    question_text = f"E2E question {question_uuid}"
    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(f"e2e_question_{question_uuid}")
    question_details_page.fill_question_hint(f"e2e_hint_{question_uuid}")
    manage_form_page = question_details_page.click_submit()
    manage_form_page.check_question_exists(question_text)


@pytest.mark.skip_in_environments(["dev", "test", "prod"])
def test_create_and_preview_schema(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser
):
    # TODO - FSPT-441: Decide if we want to create the grant in this test or not.
    new_grant_name = f"E2E create_schema_grant {uuid.uuid4()}"
    grant_dashboard_page = create_grant(new_grant_name, page, domain)
    #
    # # Go to Grant Dashboard
    # all_grants_page = AllGrantsPage(page, domain)
    # all_grants_page.navigate()
    # grant_dashboard_page = all_grants_page.click_grant(new_grant_name)

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
    create_question(QuestionDataType.TEXT_SINGLE_LINE.value, manage_form_page)
    create_question(QuestionDataType.TEXT_MULTI_LINE.value, manage_form_page)
    create_question(QuestionDataType.INTEGER.value, manage_form_page)
