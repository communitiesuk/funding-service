import re
import uuid
from typing import Callable

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import GrantScenario, GrantScenarioHandle, RecipientConfig
from tests.e2e.helpers import retrieve_magic_link
from tests.e2e.pages.access_pages import AccessHomePage, RequestALinkToSignInPage


@pytest.mark.skip_in_environments(["prod"])
def test_magic_link_redirect_journey(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    build_grant_scenario: Callable[..., GrantScenarioHandle],
):
    recipient_email = "fs-e2e-magic-link@funding-service-e2e.gov.uk"
    scenario = build_grant_scenario(
        GrantScenario(
            collection_name=f"E2E report {uuid.uuid4()}",
            org_name=f"E2E magic link org {uuid.uuid4()}",
            org_external_id=f"MHCLG-TEST-ORG-{uuid.uuid4().hex[:8].upper()}",
            recipients=[RecipientConfig(email=recipient_email, full_name="E2E Test User")],
        ),
        sign_out_after=True,
    )

    # Magic link page is no longer the default unauthenticated redirect so just go through that flow.
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    request_a_link_page.fill_email_address(recipient_email)
    request_a_link_page.click_request_a_link()

    page.wait_for_url(re.compile(rf"{domain}/check-your-email/.+"))
    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

    access_home_page = AccessHomePage(page, domain)
    access_home_page.select_grant(scenario.org_name, scenario.grant_name)
    expected_url_pattern = rf"^{domain}/access/organisation/[a-f0-9-]{{36}}/grants/[a-f0-9-]{{36}}/forms[#]?$"

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(re.compile(expected_url_pattern))
