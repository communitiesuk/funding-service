import pytest
from playwright.sync_api import Page, expect

from tests.e2e.pages import SSOSignInPage, StubSSOEmailLoginPage


@pytest.mark.skip_in_environments(["dev", "test", "prod"])
def test_sso_journey(page: Page, domain: str):
    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.navigate()
    sso_sign_in_page.click_sign_in()

    sso_email_login_page = StubSSOEmailLoginPage(page, domain)
    sso_email_login_page.fill_email_address("test@communities.gov.uk")
    sso_email_login_page.click_sign_in()

    expect(page).to_have_url(f"{domain}/grants")
