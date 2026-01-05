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


class AccessHomePage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/access")
        self.page.wait_for_load_state("networkidle")

    def select_grant(self, org_name: str, grant_name: str) -> "AccessGrantPage":
        self.page.wait_for_load_state("domcontentloaded")
        if self.page.get_by_role("link", name=org_name).is_visible():
            self.click_organisation(org_name)
            self.page.wait_for_load_state("domcontentloaded")

        if self.page.get_by_role("link", name=grant_name).is_visible():
            org_page = AccessOrganisationPage(self.page, org_name)
            org_page.click_grant(grant_name)
            self.page.wait_for_load_state("domcontentloaded")

        return AccessGrantPage(self.page, self.domain)

    def click_organisation(self, org_name: str) -> "AccessOrganisationPage":
        self.page.get_by_role("link", name=org_name).click()
        return AccessOrganisationPage(self.page, self.domain)


class AccessOrganisationPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)

    def click_grant(self, grant_name: str) -> "AccessGrantPage":
        self.page.get_by_role("link", name=grant_name).click()
        return AccessGrantPage(self.page, self.domain)


class AccessGrantPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)

    def click_collection(self, collection_name: str) -> None:
        self.page.get_by_role("link", name=collection_name).click()
