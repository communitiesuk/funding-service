import re

from playwright.sync_api import Page, expect


def test_playwright_example(page: Page):
    page.goto("https://playwright.dev/")

    # Expect a title "to contain" a substring.
    expect(page).to_have_title(re.compile("Playwright"))
