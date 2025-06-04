import uuid

import pytest
from playwright.sync_api import Page

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.pages import AllGrantsPage


@pytest.mark.skip_in_environments(["dev", "test", "prod"])
def test_create_view_edit_grant_success(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser
):
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # Set up new grant
    grant_intro_page = all_grants_page.click_set_up_a_grant()
    grant_ggis_page = grant_intro_page.click_continue()
    grant_ggis_page.select_yes()
    grant_ggis_page.fill_ggis_number()
    grant_name_page = grant_ggis_page.click_save_and_continue()
    new_grant_name = f"E2E {uuid.uuid4()}"
    grant_name_page.fill_name(new_grant_name)
    grant_description_page = grant_name_page.click_save_and_continue()
    grant_description_page.fill_description()
    grant_contact_page = grant_description_page.click_save_and_continue()
    grant_contact_page.fill_contact_name()
    grant_contact_page.fill_contact_email()
    grant_check_your_answers_page = grant_contact_page.click_save_and_continue()
    grant_confirmation_page = grant_check_your_answers_page.click_add_grant()
    grant_dashboard_page = grant_confirmation_page.click_continue()

    # On grant dashboard
    grant_dashboard_page.check_grant_name(new_grant_name)
    grant_settings_page = grant_dashboard_page.click_settings(new_grant_name)

    # Change grant name
    change_grant_name_page = grant_settings_page.click_change_grant_name(new_grant_name)
    edited_grant_name = f"{new_grant_name} - edited"
    change_grant_name_page.fill_in_grant_name(edited_grant_name)
    grant_settings_page = change_grant_name_page.click_submit(edited_grant_name)

    # Go back to Grants list and check new name appears/old name doesn't appear
    all_grants_page = grant_settings_page.click_grants()
    all_grants_page.check_grant_exists(edited_grant_name)
    all_grants_page.check_grant_doesnt_exist(new_grant_name)
