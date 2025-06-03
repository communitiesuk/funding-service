from __future__ import annotations

from abc import ABC

from playwright.sync_api import Locator, Page, expect

from tests.e2e.developer_pages import GrantDevelopersPage


class BasePage:
    domain: str
    page: Page

    def __init__(self, page: Page, domain: str) -> None:
        self.page = page
        self.domain = domain


class TopNavMixin(ABC):
    domain: str
    page: Page

    def click_grants(self) -> AllGrantsPage:
        self.page.get_by_role("link", name="Grants").click()
        return AllGrantsPage(self.page, self.domain)


class LandingPage(TopNavMixin, BasePage):
    # TODO extend once there is more stuff on the landing page
    def navigate(self) -> None:
        self.page.goto(self.domain)


class RequestALinkToSignInPage(BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Request a link to sign in")
        self.email_address = self.page.get_by_role("textbox", name="Email address")
        self.request_a_link = self.page.get_by_role("button", name="Request a link")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/request-a-link-to-sign-in")
        expect(self.title).to_be_visible()

    def fill_email_address(self, email_address: str) -> None:
        self.email_address.fill(email_address)

    def click_request_a_link(self) -> None:
        self.request_a_link.click()


class SSOSignInPage(BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Deliver grant funding")
        self.sign_in = self.page.get_by_role("button", name="Sign in")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/sso/sign-in")
        expect(self.title).to_be_visible()

    def click_sign_in(self) -> None:
        self.sign_in.click()


class StubSSOEmailLoginPage(BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Local SSO Stub Login")
        self.email_address = self.page.get_by_role("textbox", name="Email address")
        self.sign_in = self.page.get_by_role("button", name="Sign in")

    def click_sign_in(self) -> None:
        self.sign_in.click()

    def fill_email_address(self, email_address: str) -> None:
        self.email_address.fill(email_address)


class AllGrantsPage(TopNavMixin, BasePage):
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Grants")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/grants")
        expect(self.title).to_be_visible()

    def click_add_a_grant(self) -> GrantSetupIntroPage:
        self.page.get_by_role("button", name="Add a grant").click()
        grant_setup_intro_page = GrantSetupIntroPage(self.page, self.domain)
        expect(grant_setup_intro_page.title).to_be_visible()
        return grant_setup_intro_page

    def check_grant_exists(self, grant_name: str) -> None:
        expect(self.page.get_by_role("link", name=grant_name)).to_be_visible()

    def check_grant_doesnt_exist(self, grant_name: str) -> None:
        expect(self.page.get_by_role("link", name=grant_name, exact=True)).not_to_be_visible()

    def click_grant(self, grant_name: str) -> GrantDashboardPage:
        self.page.get_by_role("link", name=grant_name).click()
        grant_dashboard_page = GrantDashboardPage(self.page, self.domain)
        expect(self.page.get_by_role("heading", name=grant_name)).to_be_visible()
        return grant_dashboard_page


class GrantSetupIntroPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Tell us about the grant")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def click_continue(self) -> GrantSetupGGISPage:
        self.continue_button.click()
        grant_setup_ggis_page = GrantSetupGGISPage(self.page, self.domain)
        expect(grant_setup_ggis_page.title).to_be_visible()
        return grant_setup_ggis_page


class GrantSetupGGISPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role(
            "heading", name="Do you have a Government Grants Information System (GGIS) reference number?"
        )
        self.yes_radio = self.page.get_by_role("radio", name="Yes")
        self.ggis_number_input = self.page.get_by_role("textbox", name="Enter your GGIS reference number")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def select_yes(self) -> None:
        self.yes_radio.click()

    def fill_ggis_number(self, ggis_number: str = "ABC-123") -> None:
        self.ggis_number_input.fill(ggis_number)

    def click_save_and_continue(self) -> GrantSetupNamePage:
        self.save_continue_button.click()
        grant_setup_name_page = GrantSetupNamePage(self.page, self.domain)
        expect(grant_setup_name_page.title).to_be_visible()
        return grant_setup_name_page


class GrantSetupNamePage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the name of this grant?")
        self.name_input = self.page.get_by_role("textbox", name="What is the name of this grant?")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def fill_name(self, name: str) -> None:
        self.name_input.fill(name)

    def click_save_and_continue(self) -> GrantSetupDescriptionPage:
        self.save_continue_button.click()
        grant_setup_description_page = GrantSetupDescriptionPage(self.page, self.domain)
        expect(grant_setup_description_page.title).to_be_visible()
        return grant_setup_description_page


class GrantSetupDescriptionPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the main purpose of this grant?")
        self.description_textarea = self.page.get_by_role("textbox", name="What is the main purpose of this grant?")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def fill_description(self, description: str = "Test grant description for E2E testing purposes.") -> None:
        self.description_textarea.fill(description)

    def click_save_and_continue(self) -> GrantSetupContactPage:
        self.save_continue_button.click()
        grant_setup_contact_page = GrantSetupContactPage(self.page, self.domain)
        expect(grant_setup_contact_page.title).to_be_visible()
        return grant_setup_contact_page


class GrantSetupContactPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Who is the main contact for this grant?")
        self.contact_name_input = self.page.get_by_role("textbox", name="Full name")
        self.contact_email_input = self.page.get_by_role("textbox", name="Email address")
        self.add_grant_button = self.page.get_by_role("button", name="Add grant")

    def fill_contact_name(self, name: str = "Test Contact") -> None:
        self.contact_name_input.fill(name)

    def fill_contact_email(self, email: str = "test.contact@communities.gov.uk") -> None:
        self.contact_email_input.fill(email)

    def click_add_grant(self) -> GrantDashboardPage:
        self.add_grant_button.click()
        return GrantDashboardPage(self.page, self.domain)


class GrantDashboardBasePage(TopNavMixin, BasePage):
    dashboard_nav: Locator
    settings_nav: Locator
    developers_nav: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.dashboard_nav = self.page.get_by_role("link", name="Dashboard")
        self.settings_nav = self.page.get_by_role("link", name="Settings")
        self.developers_nav = self.page.get_by_role("link", name="Developers")

    def click_dashboard(self) -> GrantDashboardPage:
        self.dashboard_nav.click()
        return GrantDashboardPage(self.page, self.domain)

    def click_settings(self, grant_name: str) -> GrantSettingsPage:
        self.settings_nav.click()
        grant_settings_page = GrantSettingsPage(self.page, self.domain)
        expect(grant_settings_page.page.get_by_role("heading", name=f"{grant_name} Settings")).to_be_visible()
        return grant_settings_page

    def check_grant_name(self, grant_name: str) -> None:
        expect(self.page.get_by_role("heading", name=grant_name)).to_be_visible()

    def click_developers(self, grant_name: str) -> GrantDevelopersPage:
        self.developers_nav.click()
        grant_developers_page = GrantDevelopersPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_developers_page.heading).to_be_visible()
        return grant_developers_page


class GrantDashboardPage(GrantDashboardBasePage):
    pass


class GrantSettingsPage(GrantDashboardBasePage):
    change_link: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.change_link = self.page.get_by_role("link", name="Change")

    def click_change_grant_name(self, grant_name: str) -> ChangeGrantNamePage:
        self.change_link.click()
        change_grant_name_page = ChangeGrantNamePage(self.page, self.domain)
        expect(change_grant_name_page.title).to_be_visible()
        expect(change_grant_name_page.page.get_by_role("textbox", name="Grant name")).to_have_value(grant_name)
        return change_grant_name_page


class ChangeGrantNamePage(GrantDashboardBasePage):
    backlink: Locator
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.backlink = self.page.get_by_role("link", name="Back")
        self.title = self.page.get_by_role("heading", name="Grant name")

    def fill_in_grant_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="Grant name").fill(name)

    def click_submit(self, grant_name: str) -> GrantSettingsPage:
        self.page.get_by_role("button", name="Change grant name").click()
        grant_settings_page = GrantSettingsPage(self.page, self.domain)
        expect(grant_settings_page.page.get_by_role("heading", name=f"{grant_name} Settings")).to_be_visible()
        return grant_settings_page
