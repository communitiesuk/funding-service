import re

from playwright.sync_api import Page, expect

from tests.e2e.pages import LandingPage


def test_landing_page(page: Page, domain: str):
    landing_page = LandingPage(page, domain)
    landing_page.navigate()
    expect(page).to_have_title(re.compile("My grants - MHCLG Funding Service"))
