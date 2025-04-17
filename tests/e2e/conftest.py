import json
from typing import Generator

import pytest
from filelock import FileLock
from playwright.sync_api import Page
from pytest import FixtureRequest

from tests.e2e.config import AWSEndToEndSecrets, EndToEndTestSecrets, LocalEndToEndSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.helpers import generate_email_address, retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage


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
        return "https://funding.communities.gov.localhost:8080"
    if e2e_env == "dev":
        return "https://vniusepvmn.eu-west-2.awsapprunner.com"
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


def auth_with_magic_links(
    request: FixtureRequest, domain: str, e2e_test_secrets: EndToEndTestSecrets, page: Page
) -> E2ETestUser:
    email_domain_marker = request.node.get_closest_marker("user_domain")
    email_domain = email_domain_marker.args[0] if email_domain_marker else "communities.gov.uk"
    email_address = generate_email_address(test_name=request.node.originalname, email_domain=email_domain)

    # Duplicative of `test_magic_link_auth.py`, but intentionally to hopefully keep things readable/debuggable.
    email = generate_email_address(request.node.originalname)
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()

    request_a_link_page.fill_email_address(email)
    request_a_link_page.click_request_a_link()

    magic_link_url = retrieve_magic_link(email, e2e_test_secrets)
    page.goto(magic_link_url)

    return E2ETestUser(email_address=email_address)


# ideally this would be session-scoped, but the page fixture it manipulates is function-scoped
@pytest.fixture
def user_auth(
    request: FixtureRequest,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    page: Page,
    tmp_path_factory: pytest.TempPathFactory,
) -> E2ETestUser:
    # if we were scoping this fixture to session we could check here if we're not running in multiple worker mode as we
    # wouldn't need to check the file lock (the fixture would already be shared)
    # as we're scoped to function we're always using the file lock which doesn't feel great but it works
    # if worker_id == "master":
    # return auth_with_magic_links(request, domain, e2e_test_secrets, page)

    tmp_dir = tmp_path_factory.getbasetemp().parent
    fn = tmp_dir / "session.json"
    with FileLock(str(fn) + ".lock"):
        if fn.is_file():
            data = json.loads(fn.read_text())
            page.context.add_cookies([data["session"]])
            return E2ETestUser(email_address=data["email_address"])
        else:
            user = auth_with_magic_links(request, domain, e2e_test_secrets, page)
            with open(str(fn), "w") as f:
                session_cookie = next((cookie for cookie in page.context.cookies() if cookie["name"] == "session"))
                f.write(json.dumps({"session": session_cookie, "email_address": user.email_address}))
            return user
