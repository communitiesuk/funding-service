import enum
import os
import re
from typing import Generator, cast
from unittest.mock import patch

import pytest
from flask import session
from flask.typing import ResponseReturnValue
from flask_login import login_user
from playwright.sync_api import BrowserContext, Page, ViewportSize, expect
from pytest import FixtureRequest
from pytest_playwright import CreateContextCallback

from app import create_app
from app.common.data.models_user import User
from app.common.data.types import AuthMethodEnum
from tests.e2e.config import AWSEndToEndSecrets, EndToEndTestSecrets, LocalEndToEndSecrets
from tests.e2e.dataclasses import E2ETestUser, E2ETestUserConfig
from tests.e2e.helpers import retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage, SSOSignInPage, StubSSOEmailLoginPage
from tests.utils import build_db_config


class DeliverGrantFundingUserType(enum.StrEnum):
    PLATFORM_ADMIN = "platform admin"
    GRANT_TEAM_MEMBER = "grant team member"


e2e_user_configs: dict[DeliverGrantFundingUserType, E2ETestUserConfig] = {
    DeliverGrantFundingUserType.PLATFORM_ADMIN: E2ETestUserConfig(
        user_id="SSO_PLATFORM_ADMIN_USER_ID",
        email="svc-Preaward-Funds@test.communities.gov.uk",
        expected_login_url_pattern="{domain}/deliver/grants",
    ),
    DeliverGrantFundingUserType.GRANT_TEAM_MEMBER: E2ETestUserConfig(
        user_id="SSO_GRANT_TEAM_MEMBER_USER_ID",
        email="svc-Preaward-Funds@communities.gov.uk",
        expected_login_url_pattern="^{domain}/deliver/grant/[a-f0-9-]{{36}}/details$",
    ),
}


@pytest.fixture(autouse=True)
def _viewport(request: FixtureRequest, page: Page) -> None:
    width, height = request.config.getoption("viewport").split("x")
    page.set_viewport_size(ViewportSize(width=int(width), height=int(height)))


@pytest.fixture
def get_e2e_params(request: pytest.FixtureRequest) -> Generator[dict[str, str], None, None]:
    e2e_env = request.config.getoption("e2e_env", "local")
    yield {
        "e2e_env": e2e_env,
    }


@pytest.fixture()
def domain(request: pytest.FixtureRequest, get_e2e_params: dict[str, str]) -> str:
    e2e_env = get_e2e_params["e2e_env"]

    if e2e_env == "local":
        return "https://funding.communities.gov.localhost:8080"
    if e2e_env == "dev":
        return "https://funding.dev.communities.gov.uk"
    if e2e_env == "test":
        return "https://funding.test.communities.gov.uk"
    else:
        raise ValueError(f"not configured for {e2e_env}")


@pytest.fixture
def e2e_test_secrets(request: FixtureRequest) -> EndToEndTestSecrets:
    e2e_env = request.config.getoption("e2e_env")
    e2e_aws_vault_profile = request.config.getoption("e2e_aws_vault_profile")

    if e2e_env == "local":
        return LocalEndToEndSecrets()

    if e2e_env in {"dev", "test"}:
        return AWSEndToEndSecrets(e2e_env=e2e_env, e2e_aws_vault_profile=e2e_aws_vault_profile)

    raise ValueError(f"Unknown e2e_env: {e2e_env}.")


@pytest.fixture(autouse=True)
def context(
    new_context: CreateContextCallback,
    request: pytest.FixtureRequest,
    e2e_test_secrets: EndToEndTestSecrets,
    get_e2e_params: dict[str, str],
) -> BrowserContext:
    e2e_env = get_e2e_params["e2e_env"]
    http_credentials = e2e_test_secrets.HTTP_BASIC_AUTH if e2e_env in {"dev", "test"} else None
    return new_context(http_credentials=http_credentials)


@pytest.fixture()
def email(request: FixtureRequest) -> str:
    return cast(str, request.node.get_closest_marker("authenticate_as", "funding-service-notify@communities.gov.uk"))


@pytest.fixture()
def authenticated_browser_magic_link(
    domain: str, e2e_test_secrets: EndToEndTestSecrets, page: Page, email: str
) -> E2ETestUser:
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()

    request_a_link_page.fill_email_address(email)
    request_a_link_page.click_request_a_link()

    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

    return E2ETestUser(email_address=email)


def login_with_stub_sso(domain: str, page: Page, email: str, user_type: DeliverGrantFundingUserType) -> E2ETestUser:
    """
    Logs in using the stub SSO flow, used for local development and running tests against docker compose in github
    """
    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.navigate()
    sso_sign_in_page.click_sign_in()

    sso_email_login_page = StubSSOEmailLoginPage(page, domain)
    sso_email_login_page.fill_email_address(email)
    if user_type == DeliverGrantFundingUserType.GRANT_TEAM_MEMBER:
        sso_email_login_page.uncheck_platform_admin_checkbox()
    sso_email_login_page.click_sign_in()

    return E2ETestUser(email_address=email)


def login_with_session_cookie(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, user_type: DeliverGrantFundingUserType
) -> E2ETestUser:
    """
    Creates an instance of the app with an additional route that uses flask_login to log in the test user. Retrieves the
    session cookie from the response headers and adds it to the browser context cookies. Then that browser behaves as if
    it is logged in with a valid session cookie. This bypasses the need to use the real SSO flow.

    """
    user_config = e2e_user_configs[user_type]

    user_obj = User(name="E2E Test User", id=getattr(e2e_test_secrets, user_config.user_id))
    with patch.dict(os.environ, build_db_config(None)):
        new_app = create_app()
    new_app.config["SECRET_KEY"] = e2e_test_secrets.SECRET_KEY

    @new_app.route("/fake_login")
    def fake_login() -> ResponseReturnValue:
        login_user(user=user_obj, fresh=True)
        session["auth"] = AuthMethodEnum.SSO
        return "OK"

    with new_app.test_request_context():
        test_client = new_app.test_client()
        result = test_client.get("/fake_login")
        assert result.status_code == 200, "Fake login did not return 200 OK"
        cookies = result.headers.get("Set-Cookie", None)
        cookie_value = cookies.split(";")[0].split("=")[1] if cookies else None
        if not cookie_value:
            raise pytest.fail(
                f"Unable to extract session cookie value from fake-login response headers: {result.headers}"
            )

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

    url_pattern = user_config.expected_login_url_pattern.format(domain=domain)
    expected_url: str | re.Pattern[str]
    if url_pattern.startswith("^"):
        expected_url = re.compile(url_pattern)
    else:
        expected_url = url_pattern

    # If the browser contains a valid cookie, it should redirect to the grants page or a specific grant page
    expect(page).to_have_url(expected_url)
    return E2ETestUser(email_address=user_config.email)


@pytest.fixture()
def authenticated_browser_sso(
    domain: str, e2e_test_secrets: EndToEndTestSecrets, page: Page, email: str
) -> E2ETestUser:
    if e2e_test_secrets.E2E_ENV == "local":
        return login_with_stub_sso(domain, page, email, DeliverGrantFundingUserType.PLATFORM_ADMIN)
    elif e2e_test_secrets.E2E_ENV in {"dev", "test"}:
        return login_with_session_cookie(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN)
    else:
        raise ValueError(f"Unknown e2e_env: {e2e_test_secrets.E2E_ENV}. Cannot authenticate browser with SSO.")
