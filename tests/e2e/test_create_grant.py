from playwright.sync_api import Page, expect

from tests.e2e.conftest import FundingServiceDomains


def test_create_grant(page: Page, domains: FundingServiceDomains):
    page.goto(f"{domains.landing_url}/grants")
    expect(page).to_have_title("All grants - MHCLG Funding Service")
