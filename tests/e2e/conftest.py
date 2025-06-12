from typing import Generator, cast

import pytest
from playwright.sync_api import BrowserContext, Page
from pytest import FixtureRequest
from pytest_playwright import CreateContextCallback

from tests.e2e.config import AWSEndToEndSecrets, EndToEndTestSecrets, LocalEndToEndSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.helpers import retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage, SSOSignInPage, StubSSOEmailLoginPage


@pytest.fixture(autouse=True)
def _viewport(request: FixtureRequest, page: Page) -> None:
    width, height = request.config.getoption("viewport").split("x")
    page.set_viewport_size({"width": int(width), "height": int(height)})


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
        return "http://localhost:8080"
        # return "https://funding.communities.gov.localhost:8080"
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


@pytest.fixture()
def authenticated_browser_sso(
    domain: str, e2e_test_secrets: EndToEndTestSecrets, page: Page, email: str
) -> E2ETestUser:
    sso_sign_in_page = SSOSignInPage(page, domain)
    sso_sign_in_page.navigate()
    sso_sign_in_page.click_sign_in()

    sso_email_login_page = StubSSOEmailLoginPage(page, domain)
    sso_email_login_page.fill_email_address(email)
    sso_email_login_page.click_sign_in()

    return E2ETestUser(email_address=email)
