import uuid

from playwright.sync_api import Page

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.pages import AllGrantsPage


def test_create_view_edit_grant_success(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser: E2ETestUser
):
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # Set up new grant
    new_grant_page = all_grants_page.click_set_up_new_grant()
    new_grant_name = f"E2E {uuid.uuid4()}"
    new_grant_page.fill_in_grant_name(new_grant_name)
    all_grants_page = new_grant_page.click_submit()
    all_grants_page.check_grant_exists(new_grant_name)

    # Go to Grant Dashboard
    grant_dashboard_page = all_grants_page.click_grant(new_grant_name)
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
