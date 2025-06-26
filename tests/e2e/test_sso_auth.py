from os import getenv

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.pages import MicrosoftLoginPageEmail, SSOSignInPage, StubSSOEmailLoginPage


@pytest.mark.skip_in_environments(["dev", "test", "prod"])
def test_stub_sso_journey(page: Page, domain: str):
    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.navigate()
    sso_sign_in_page.click_sign_in()

    sso_email_login_page = StubSSOEmailLoginPage(page, domain)
    sso_email_login_page.fill_email_address("test@communities.gov.uk")
    sso_email_login_page.click_sign_in()

    expect(page).to_have_url(f"{domain}/grants")


@pytest.mark.skip_in_environments(["local", "dev", "test", "prod"])
def test_real_sso_journey(page: Page, domain: str):
    """
    Test the real SSO journey using a service account.

    If you enable real SSO locally (see README) this test will work.
    However we can't run it on CI - see Jira FSPT-411 for details.
    :param page:
    :param domain:
    :return:
    """
    sign_in_email = getenv("SERVICE_ACCOUNT_USERNAME", None)
    sign_in_password = getenv("SERVICE_ACCOUNT_PASSWORD", None)
    if not sign_in_email or not sign_in_password:
        pytest.fail("SERVICE_ACCOUNT_USERNAME and SERVICE_ACCOUNT_PASSWORD must be set for this test")
    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.navigate()
    sso_sign_in_page.click_sign_in()
    ms_email_page = MicrosoftLoginPageEmail(page, domain, sign_in_email, sign_in_password)
    ms_email_page.fill_email_address()
    ms_password_page = ms_email_page.click_next()
    ms_password_page.fill_password()
    ms_password_page.click_sign_in()

    if not page.url == f"{domain}/grants":
        page.get_by_role("link", name="Click here for more details").click()
        page.screenshot()
        pytest.fail("SSO login did not redirect to /grants as expected")

    expect(page).to_have_url(f"{domain}/grants")
