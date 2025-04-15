from typing import Generator

import pytest
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
        return "https://vniusepvmn.eu-west-2.awsapprunner.com/"
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


@pytest.fixture()
def user_auth(
    request: FixtureRequest,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    page: Page,
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
