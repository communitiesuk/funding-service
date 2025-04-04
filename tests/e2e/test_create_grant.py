from playwright.sync_api import Page, expect

from tests.e2e.conftest import FundingServiceDomains
from tests.e2e.pages import (
    AllGrantsPage,
    NewGrantDuplicateNameErrorPage,
    NewGrantErrorPage,
    NewGrantIncompleteErrorPage,
    NewGrantPage,
)


def test_create_grant_success(page: Page, domains: FundingServiceDomains):
    all_grants_page = AllGrantsPage(page, domains.landing_url)
    all_grants_page.navigate()
    expect(all_grants_page.get_title()).to_be_visible()

    new_grant_page: NewGrantPage = all_grants_page.click_set_up_new_grant()
    expect(page.get_by_role("heading", name="Set up a new grant")).to_be_visible()

    # TODO generate unique names
    new_grant_name = "Test name 15"
    new_grant_page.complete_grant_name(new_grant_name)
    all_grants_page: AllGrantsPage = new_grant_page.submit_new_grant_form(AllGrantsPage)

    expect(all_grants_page.get_title()).to_be_visible()
    expect(page.get_by_role("link").filter(has_text=new_grant_name)).to_be_visible()

    # Check validation errors
    new_grant_page: NewGrantPage = all_grants_page.click_set_up_new_grant()
    expect(page.get_by_role("heading", name="Set up a new grant")).to_be_visible()

    # Submit with no grant name
    error_page: NewGrantErrorPage = new_grant_page.submit_new_grant_form(NewGrantIncompleteErrorPage)
    expect(error_page.get_error_title()).to_be_visible()
    expect(error_page.get_error_subtitle()).to_be_visible()

    # Use previous grant name
    new_grant_page.complete_grant_name(new_grant_name)
    error_page: NewGrantErrorPage = new_grant_page.submit_new_grant_form(NewGrantDuplicateNameErrorPage)
    expect(error_page.get_error_title()).to_be_visible()
    expect(error_page.get_error_subtitle()).to_be_visible()
