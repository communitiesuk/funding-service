import re

from _pytest.fixtures import FixtureRequest
from playwright.sync_api import Page, expect

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.helpers import generate_email_address, retrieve_magic_link
from tests.e2e.pages import RequestALinkToSignInPage


def test_magic_link_redirect_journey(
    request: FixtureRequest, page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets
):
    page.goto(f"{domain}/grants")

    # Redirected to request a magic link page; go through that flow.
    email = generate_email_address(request.node.originalname)
    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.fill_email_address(email)
    request_a_link_page.click_request_a_link()

    page.wait_for_url(re.compile(rf"{domain}/check-your-email/.+"))

    magic_link_url = retrieve_magic_link(email, e2e_test_secrets)
    page.goto(magic_link_url)

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(f"{domain}/grants")
