from playwright.sync_api import Page


def test_start_chrome(page: Page):
    """Test to ensure that the Playwright setup is working correctly by navigating to Google.
    Used in the e2e test pipeline to launch chrome before we generate certificates so that the
    chrome security database exists and make certs can write the CA to it.
    """
    page.goto("https://google.com")
