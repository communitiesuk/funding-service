import uuid

from playwright.sync_api import Page, expect

from tests.e2e.conftest import FundingServiceDomains
from tests.e2e.pages import (
    AllGrantsPage,
    NewGrantPage,
)


def test_create_grant_success(page: Page, domains: FundingServiceDomains):
    all_grants_page = AllGrantsPage(page, domains.landing_url)
    all_grants_page.navigate()
    expect(all_grants_page.title).to_be_visible()

    new_grant_page: NewGrantPage = all_grants_page.click_set_up_new_grant()
    expect(page.get_by_role("heading", name="Set up a new grant")).to_be_visible()

    new_grant_name = f"E2E {uuid.uuid4()}"
    new_grant_page.complete_grant_name(new_grant_name)
    all_grants_page: AllGrantsPage = new_grant_page.submit_new_grant_form(AllGrantsPage)

    expect(all_grants_page.title).to_be_visible()
    expect(page.get_by_role("link").filter(has_text=new_grant_name)).to_be_visible()

    # Check validation errors
    new_grant_page: NewGrantPage = all_grants_page.click_set_up_new_grant()
    expect(page.get_by_role("heading", name="Set up a new grant")).to_be_visible()

    # Submit with no grant name
    new_grant_page.submit_new_grant_form(NewGrantPage)
    expect(new_grant_page.get_error_title("There is a problem")).to_be_visible()
    expect(new_grant_page.get_error_subtitle("Enter a grant name")).to_be_visible()

    # Use previous grant name
    new_grant_page.complete_grant_name(new_grant_name)
    new_grant_page.submit_new_grant_form(NewGrantPage)
    expect(new_grant_page.get_error_title("There is a problem")).to_be_visible()
    expect(new_grant_page.get_error_subtitle("Grant name already in use")).to_be_visible()
