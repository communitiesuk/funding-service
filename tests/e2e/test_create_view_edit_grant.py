import uuid

from playwright.sync_api import Page, expect

from tests.e2e.conftest import FundingServiceDomains
from tests.e2e.pages import AllGrantsPage, ChangeGrantNamePage, GrantDashboardPage, GrantSettingsPage, NewGrantPage


def test_create_view_edit_grant_success(page: Page, domains: FundingServiceDomains):
    all_grants_page = AllGrantsPage(page, domains.landing_url)
    all_grants_page.navigate()
    expect(all_grants_page.title).to_be_visible()

    # Set up new grant
    new_grant_page: NewGrantPage = all_grants_page.click_set_up_new_grant()
    expect(new_grant_page.title).to_be_visible()

    new_grant_name = f"E2E {uuid.uuid4()}"
    new_grant_page.complete_grant_name(new_grant_name)
    all_grants_page: AllGrantsPage = new_grant_page.submit_new_grant_form(AllGrantsPage)

    expect(all_grants_page.title).to_be_visible()
    expect(page.get_by_role("link", name=new_grant_name)).to_be_visible()

    # Check validation errors
    new_grant_page: NewGrantPage = all_grants_page.click_set_up_new_grant()

    # Submit form with no grant name
    new_grant_page.submit_new_grant_form(NewGrantPage)
    expect(new_grant_page.get_error_title("There is a problem")).to_be_visible()
    expect(new_grant_page.get_error_subtitle("Enter a grant name")).to_be_visible()

    # Submit form with a pre-existing grant name
    new_grant_page.complete_grant_name(new_grant_name)
    new_grant_page.submit_new_grant_form(NewGrantPage)
    expect(new_grant_page.get_error_title("There is a problem")).to_be_visible()
    expect(new_grant_page.get_error_subtitle("Grant name already in use")).to_be_visible()

    # Grant Dashboard
    new_grant_page.backlink.click()
    page.get_by_role("link", name=new_grant_name).click()
    grant_dashboard_page = GrantDashboardPage(page, domains.landing_url)
    expect(page.get_by_role("heading", name=new_grant_name)).to_be_visible()

    # Grant Settings
    grant_settings_page: GrantSettingsPage = grant_dashboard_page.go_to_settings()
    expect(page.get_by_role("heading", name=f"{new_grant_name} Settings")).to_be_visible()

    # Change grant name
    change_grant_name_page: ChangeGrantNamePage = grant_settings_page.go_to_change_grant_name()
    expect(change_grant_name_page.title).to_be_visible()
    expect(page.get_by_role("textbox", name="Grant name")).to_be_visible()
    expect(page.get_by_role("textbox", name="Grant name")).to_have_value(new_grant_name)

    edited_grant_name = f"E2E {uuid.uuid4()}"
    change_grant_name_page.complete_grant_name(edited_grant_name)
    change_grant_name_page.submit_change_grant_name_form(GrantSettingsPage)
    expect(page.get_by_role("heading", name=f"{edited_grant_name} Settings")).to_be_visible()

    # Go back to Grants list and check new name appears and old name doesn't appear
    page.get_by_role("link", name="Grants").click()
    expect(page.get_by_role("link", name=edited_grant_name)).to_be_visible()
    expect(page.get_by_role("link", name=new_grant_name)).not_to_be_visible()
