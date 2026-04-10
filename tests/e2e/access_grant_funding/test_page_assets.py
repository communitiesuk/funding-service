from playwright.sync_api import Page

from tests.e2e.access_grant_funding.pages import RequestALinkToSignInPage


def test_missing_or_failed_assets(page: Page, domain: str):
    missing_assets = []

    def handle_response(response):
        if response.status >= 400:
            missing_assets.append(response.url)

    page.on("response", handle_response)

    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate(wait_for_network_idle=True)

    assert len(missing_assets) == 0, f"Missing or failed assets:\n{'\n'.join(missing_assets)}"
