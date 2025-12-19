from abc import ABC
from typing import Self

from playwright.sync_api import Page, expect

from tests.e2e.pages import BasePage


class CookieBannerMixin(ABC):
    domain: str
    page: Page

    def click_accept_cookies(self) -> Self:
        self.page.get_by_role("button", name="Accept analytics cookies").click()
        return self

    def click_reject_cookies(self) -> Self:
        self.page.get_by_role("button", name="Reject analytics cookies").click()
        return self

    def click_hide_cookies(self) -> Self:
        self.page.get_by_role("button", name="Hide cookie message").click()
        return self


class RequestALinkToSignInPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Access grant funding", exact=True)
        self.email_address = self.page.get_by_role("textbox", name="Email address")
        self.request_a_link = self.page.get_by_role("button", name="Request sign in link")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/request-a-link-to-sign-in")
        expect(self.title).to_be_visible()

    def fill_email_address(self, email_address: str) -> None:
        self.email_address.fill(email_address)

    def click_request_a_link(self) -> None:
        self.request_a_link.click()
