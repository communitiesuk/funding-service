import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.access_grant_funding.pages import AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser

_shared_access_data = {
    "grant_name": "Cheeseboards in parks",
    "organisation_name": "MHCLG Funding Service Test Organisation",
}


@pytest.mark.authenticate_as("fsd-post-award@levellingup.gov.uk")
def test_complete_and_submit_report(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_magic_link: E2ETestUser,
    email: str,
) -> None:
    data = _shared_access_data
    access_home_page = AccessHomePage(page, domain)
    access_home_page.select_grant(data["organisation_name"], data["grant_name"])
    expected_url_pattern = rf"^{domain}/access/organisation/[a-f0-9-]{{36}}/grants/[a-f0-9-]{{36}}/reports[#]?$"

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(re.compile(expected_url_pattern))
