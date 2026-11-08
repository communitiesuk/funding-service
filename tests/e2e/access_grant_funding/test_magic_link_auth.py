import re
import uuid
from typing import Callable

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.access_grant_funding.pages import AccessHomePage, RequestALinkToSignInPage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import (
    BuiltGrantScenario,
    CollectionConfig,
    DataProviderConfig,
    GrantScenario,
    OrganisationConfig,
)
from tests.e2e.helpers import retrieve_magic_link


@pytest.mark.skip_in_environments(["prod"])
def test_magic_link_redirect_journey(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    build_grant_scenario: Callable[..., BuiltGrantScenario],
):
    org_uuid = uuid.uuid4()
    org_name = f"E2E Testing Organisation {org_uuid}"
    user_email = "fs-e2e-magic-link-auth@funding-service-e2e.gov.uk"

    handle = build_grant_scenario(
        GrantScenario(
            collection=CollectionConfig(name=f"E2E magic link report {uuid.uuid4()}"),
            organisations=[
                OrganisationConfig(
                    name=org_name,
                    external_id=f"MHCLG-TEST-ORG-{org_uuid}",
                    data_providers=[DataProviderConfig(email=user_email, full_name="MHCLG Test User")],
                )
            ],
        ),
        sign_out_after=True,
    )

    # Magic link page is no longer the default unauthenticated redirect so just go through that flow.
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    request_a_link_page.fill_email_address(user_email)
    request_a_link_page.click_request_a_link()

    page.wait_for_url(re.compile(rf"{domain}/check-your-email/.+"))
    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

    access_home_page = AccessHomePage(page, domain)
    access_home_page.select_grant(org_name, handle.grant_name)
    expected_url_pattern = rf"^{domain}/access/organisation/[a-f0-9-]{{36}}/grants/[a-f0-9-]{{36}}/forms[#]?$"

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(re.compile(expected_url_pattern))
