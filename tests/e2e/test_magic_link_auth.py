import re

from playwright.sync_api import Page, expect

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.helpers import retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage


def test_magic_link_redirect_journey(page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, email: str):
    # Magic link page is no longer the default unauthenticated redirect so just go through that flow.
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    request_a_link_page.fill_email_address(email)
    request_a_link_page.click_request_a_link()

    page.wait_for_url(re.compile(rf"{domain}/check-your-email/.+"))
    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(f"{domain}/grants")
