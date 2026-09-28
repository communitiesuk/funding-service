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
        self.request_a_link = self.page.get_by_role("button", name="Sign in with link")

    def navigate(self, *, wait_for_network_idle: bool = False) -> None:
        self.page.goto(
            f"{self.domain}/request-a-link-to-sign-in", wait_until="networkidle" if wait_for_network_idle else None
        )
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


class PublicSignUpStartPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.start_now_button = self.page.get_by_role("button", name="Start now")

    def click_start_now(self) -> "PublicSignUpRequestALinkPage":
        self.start_now_button.click()
        request_a_link_page = PublicSignUpRequestALinkPage(self.page, self.domain)
        expect(request_a_link_page.email_address).to_be_visible()
        return request_a_link_page


class PublicSignUpRequestALinkPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.email_address = self.page.get_by_role("textbox", name="Enter your work email address")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def fill_email_address(self, email_address: str) -> None:
        self.email_address.fill(email_address)

    def click_continue(self) -> None:
        self.continue_button.click()


class PublicSignUpEligibilityQuestionPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str, question_text: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name=question_text)
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def click_yes(self) -> None:
        self.page.get_by_role("radio", name="Yes").click()

    def click_no(self) -> None:
        self.page.get_by_role("radio", name="No").click()

    def click_continue(self) -> None:
        self.continue_button.click()


class PublicSignUpIneligiblePage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name="You are not eligible to apply")
        self.back_link = self.page.get_by_role("link", name="Back", exact=True)

    def click_back(self) -> None:
        self.back_link.click()


class EligibleToApplyPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name="You are eligible to apply")
        self.create_an_organisation_button = self.page.get_by_role("button", name="Create an organisation")

    def click_create_an_organisation(self) -> None:
        self.create_an_organisation_button.click()


class CreateOrganisationTypePage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name="What is your organisation type?")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def select_other(self) -> None:
        self.page.get_by_role("radio", name="Other", exact=True).click()

    def click_continue(self) -> None:
        self.continue_button.click()


class CreateOrganisationNamePage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name="What is the name of your organisation?")
        self.name = self.page.get_by_role("textbox", name="What is the name of your organisation?")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def fill_name(self, name: str) -> None:
        self.name.fill(name)

    def click_continue(self) -> None:
        self.continue_button.click()


class CreateOrganisationAllowTeamMembersPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def click_yes(self) -> None:
        self.page.get_by_role("radio", name="Yes").click()

    def click_continue(self) -> None:
        self.continue_button.click()


class CreateOrganisationUserNamePage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name="What is your full name?")
        self.user_name = self.page.get_by_role("textbox", name="What is your full name?")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def fill_user_name(self, name: str) -> None:
        self.user_name.fill(name)

    def click_continue(self) -> None:
        self.continue_button.click()


class CreateOrganisationCheckYourAnswersPage(CookieBannerMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.heading = self.page.get_by_role("heading", name="Confirm your details are correct")
        self.confirm_button = self.page.get_by_role("button", name="Confirm and create organisation")

    def click_confirm(self) -> None:
        self.confirm_button.click()
