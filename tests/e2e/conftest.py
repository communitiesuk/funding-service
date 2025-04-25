import json
from http.cookiejar import Cookie
from typing import Generator, cast

import pytest
from filelock import FileLock
from playwright.sync_api import Browser, BrowserContext, Page
from pytest import FixtureRequest
from pytest_playwright import CreateContextCallback

from tests.e2e.config import AWSEndToEndSecrets, EndToEndTestSecrets, LocalEndToEndSecrets
from tests.e2e.helpers import retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage


@pytest.fixture(autouse=True)
def _viewport(request: FixtureRequest, page: Page) -> None:
    width, height = request.config.getoption("viewport").split("x")
    page.set_viewport_size({"width": int(width), "height": int(height)})


@pytest.fixture(scope="session")
def get_e2e_params(request: pytest.FixtureRequest) -> Generator[dict[str, str], None, None]:
    e2e_env = request.config.getoption("e2e_env", "local")
    yield {
        "e2e_env": e2e_env,
    }


@pytest.fixture(scope="session")
def domain(request: pytest.FixtureRequest, get_e2e_params: dict[str, str]) -> str:
    e2e_env = get_e2e_params["e2e_env"]

    if e2e_env == "local":
        return "https://funding.communities.gov.localhost:8080"
    if e2e_env == "dev":
        return "https://mjq6qj6jmg.eu-west-2.awsapprunner.com"
    if e2e_env == "test":
        return "https://9zmqrmjg7a.eu-west-2.awsapprunner.com"
    else:
        raise ValueError(f"not configured for {e2e_env}")


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def email(request: FixtureRequest) -> str:
    return cast(str, request.node.get_closest_marker("authenticate_as", "funding-service-notify@communities.gov.uk"))


@pytest.fixture(scope="function")
def authenticated_browser(authenticated_browser_session: Cookie, page: Page) -> Page:
    # a cleaner way to do this is new_context - see context override above but not spending time on it
    page.context.add_cookies([authenticated_browser_session])  # type: ignore
    return page


# This is just a proof of concept, the methodology would actually be to have all
# the users you want to be able to use listed as an enum. Those users would all be
# initialised by the session fixture once at the start and then the function scope fixture would just return
# the session for a given email in a dict lookup
@pytest.fixture(scope="session")
def authenticated_browser_session(
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    browser: Browser,
    email: str,
    tmp_path_factory: pytest.TempPathFactory,
    get_e2e_params: dict[str, str],
    worker_id: str,
) -> Cookie:
    if worker_id == "master":
        session_cookie = authenticate_with_magic_links(domain, e2e_test_secrets, browser, email, get_e2e_params)
        return session_cookie

    tmp_dir = tmp_path_factory.getbasetemp().parent

    fn = tmp_dir / f"{email}-session.json"
    with FileLock(str(fn) + ".lock"):
        if fn.is_file():
            data = json.loads(fn.read_text())
            return cast(Cookie, data["session"])
        else:
            session_cookie = authenticate_with_magic_links(domain, e2e_test_secrets, browser, email, get_e2e_params)
            with open(str(fn), "w") as f:
                f.write(json.dumps({"session": session_cookie, "email_address": email}))
            return session_cookie


def authenticate_with_magic_links(
    domain: str, e2e_test_secrets: EndToEndTestSecrets, browser: Browser, email: str, get_e2e_params: dict[str, str]
) -> Cookie:
    e2e_env = get_e2e_params["e2e_env"]
    http_credentials = e2e_test_secrets.HTTP_BASIC_AUTH if e2e_env in {"dev", "test"} else None
    page = browser.new_page(http_credentials=http_credentials)

    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()

    request_a_link_page.fill_email_address(email)
    request_a_link_page.click_request_a_link()

    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

    session_cookie = next((cookie for cookie in page.context.cookies() if cookie["name"] == "session"))
    page.close()
    return cast(Cookie, session_cookie)
