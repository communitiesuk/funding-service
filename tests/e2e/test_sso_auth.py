import os
from os import getenv
from unittest.mock import patch

import pytest
from flask_login import login_user
from playwright.sync_api import BrowserContext, Page, expect

from app import create_app
from app.common.data.models_user import User
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.pages import MicrosoftLoginPageEmail, SSOSignInPage, StubSSOEmailLoginPage
from tests.utils import build_db_config


@pytest.mark.skip_in_environments(["local", "dev", "test", "prod"])
def test_stub_sso_journey(page: Page, domain: str):
    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.navigate()
    sso_sign_in_page.click_sign_in()

    sso_email_login_page = StubSSOEmailLoginPage(page, domain)
    sso_email_login_page.fill_email_address("test@communities.gov.uk")
    sso_email_login_page.click_sign_in()

    expect(page).to_have_url(f"{domain}/grants")


# @pytest.mark.skip_in_environments(["local"])
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


def test_login_with_fake_cookie(
    page: Page, domain: str, context: BrowserContext, e2e_test_secrets: EndToEndTestSecrets
):
    # TODO use id of a real user in dev/test
    user_obj = User(name="E2E Test User", id=e2e_test_secrets.SSO_USER_ID)
    with patch.dict(os.environ, build_db_config(None)):
        new_app = create_app()
    new_app.config["SECRET_KEY"] = e2e_test_secrets.SECRET_KEY

    @new_app.route("/fake_login")
    def fake_login():
        login_user(user=user_obj, fresh=True)
        return "OK"

    with new_app.test_request_context():
        login_user(user=user_obj, fresh=True)
        test_client = new_app.test_client()
        result = test_client.get("/fake_login")
        assert result.status_code == 200, "Fake login did not return 200 OK"
        cookies = result.headers.get("Set-Cookie", None)
        cookie_value = cookies.split(";")[0].split("=")[1] if cookies else None

    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.page.context.add_cookies(
        [
            {
                "name": "session",
                "value": cookie_value,
                "domain": domain.split("https://")[1].split(":8080")[0],
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
        ]
    )
    sso_sign_in_page.navigate()
    # If the browser contains a valid cookie, it should redirect to the grants page
    expect(page).to_have_url(f"{domain}/grants")
