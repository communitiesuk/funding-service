import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.helpers import retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage


@pytest.mark.skip_in_environments(["local", "dev", "test", "prod"])
def test_magic_link_redirect_journey(page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets):
    # Magic link page is no longer the default unauthenticated redirect so just go through that flow.
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    request_a_link_page.fill_email_address("fsd-post-award@levellingup.gov.uk")
    request_a_link_page.click_request_a_link()

    page.wait_for_url(re.compile(rf"{domain}/check-your-email/.+"))
    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

    expected_url_pattern = rf"^{domain}/organisation/[a-f0-9-]{{36}}/grants$"

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(re.compile(expected_url_pattern))
