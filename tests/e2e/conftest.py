import enum
import os
import uuid
from typing import Callable, Generator, cast
from unittest.mock import patch

import pytest
from flask import session
from flask.typing import ResponseReturnValue
from flask_login import login_user
from playwright.sync_api import BrowserContext, Page, ViewportSize
from pytest import FixtureRequest
from pytest_playwright import CreateContextCallback

from app.common.data.models_user import User
from app.common.data.types import AuthMethodEnum
from tests.conftest import create_test_app
from tests.e2e.access_grant_funding.pages import RequestALinkToSignInPage
from tests.e2e.config import AWSEndToEndSecrets, EndToEndTestSecrets, LocalEndToEndSecrets
from tests.e2e.dataclasses import E2ETestUser, E2ETestUserConfig, GrantScenario, GrantScenarioHandle
from tests.e2e.deliver_grant_funding.helpers import (
    create_collection,
    create_grant,
    create_grant_recipient,
    create_organisation,
    extract_uuid_from_url,
    invite_data_providers,
    mark_as_onboarding,
    override_certifiers,
    set_grant_and_collection_live,
    set_privacy_policy,
    set_reporting_and_submission_dates,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, SSOSignInPage, StubSSOEmailLoginPage
from tests.e2e.deliver_grant_funding.reports_pages import AdminCollectionLifecycleTasklistPage
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
    delete_organisation_through_admin,
    retrieve_magic_link,
)
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
        email="fsd-post-award@communities.gov.uk",
        expected_login_url_pattern="^{domain}/deliver/grant/[a-f0-9-]{{36}}/reports$",
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
        new_app = create_test_app()
    new_app.config["SECRET_KEY"] = e2e_test_secrets.SECRET_KEY

    @new_app.route("/fake_login")
    def fake_login() -> ResponseReturnValue:
        login_user(user=user_obj, fresh=True)
        session["auth"] = AuthMethodEnum.SSO
        return "OK", 200, {"Content-Type": "text/plain"}

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
            },
        ]
    )
    sso_sign_in_page.navigate()

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


@pytest.fixture()
def build_grant_scenario(  # noqa: C901 -- orchestrates many independently-simple, opt-in steps; see helpers above
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> Generator[Callable[..., GrantScenarioHandle], None, None]:
    """Factory fixture: builds a grant + collection + organisation + recipient(s) from a `GrantScenario` spec, and
    tears down everything it built (regardless of which scenarios were requested) once the test finishes.

    Teardown re-authenticates as platform admin before cleaning up, since the test body is free to sign out and/or
    switch to a different identity (e.g. to drive a magic-link/recipient journey) after calling this fixture."""
    created_handles: list[GrantScenarioHandle] = []

    def _build(scenario: GrantScenario, *, sign_out_after: bool = False) -> GrantScenarioHandle:
        grant_name_uuid = str(uuid.uuid4())
        grant_name = f"E2E {grant_name_uuid}"

        all_grants_page = AllGrantsPage(page, domain)
        all_grants_page.navigate()
        grant_dashboard_page = create_grant(grant_name, grant_name_uuid, all_grants_page)
        grant_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")

        collection_id: str | None = None
        tasklist_page: AdminCollectionLifecycleTasklistPage | None = None

        if scenario.collection_name:
            collection_id, tasklist_page = create_collection(
                page, domain, grant_id, grant_name, scenario.collection_name, grant_dashboard_page
            )

        if scenario.org_name:
            assert collection_id is not None
            create_organisation(page, domain, grant_id, collection_id, scenario)
            create_grant_recipient(page, domain, grant_id, collection_id, scenario)

            if scenario.recipients:
                invite_data_providers(page, domain, grant_id, collection_id, scenario)

            if scenario.set_certifiers and scenario.recipients:
                assert tasklist_page is not None
                override_certifiers(page, domain, grant_id, collection_id, tasklist_page, scenario)

        if collection_id is not None and tasklist_page is not None:
            if scenario.set_dates:
                assert scenario.collection_name is not None
                set_reporting_and_submission_dates(
                    page, domain, grant_id, collection_id, scenario.collection_name, tasklist_page
                )

            if scenario.mark_onboarding:
                mark_as_onboarding(page, domain, grant_id, collection_id, tasklist_page)

            if scenario.set_privacy_policy:
                set_privacy_policy(page, domain, grant_id, collection_id, tasklist_page)

            if scenario.set_live:
                set_grant_and_collection_live(page, domain, grant_id, collection_id)

        handle = GrantScenarioHandle(
            grant_id=grant_id,
            grant_name=grant_name,
            grant_name_uuid=grant_name_uuid,
            collection_id=collection_id,
            report_name=scenario.collection_name,
            org_name=scenario.org_name,
        )
        created_handles.append(handle)

        if sign_out_after:
            page.goto(f"{domain}/sign-out")

        return handle

    yield _build

    if created_handles:
        page.goto(f"{domain}/sign-out")
        if e2e_test_secrets.E2E_ENV == "local":
            login_with_stub_sso(domain, page, email, DeliverGrantFundingUserType.PLATFORM_ADMIN)
        else:
            login_with_session_cookie(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN)

    for handle in created_handles:
        if handle.org_name is not None:
            delete_grant_recipient_through_admin(
                page, domain, handle.grant_name_uuid, expected_grant_recipients_matching_search=2
            )
            delete_organisation_through_admin(page, domain, handle.org_name, expected_organisations_matching_search=2)
        delete_grant_through_admin(page, domain, handle.grant_name_uuid)
