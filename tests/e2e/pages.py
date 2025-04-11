from __future__ import annotations

from abc import ABC
from typing import Type, TypeVar

from playwright.sync_api import Locator, Page


class BasePage:
    domain: str
    page: Page

    def __init__(self, page: Page, domain: str) -> None:
        self.page = page
        self.domain = domain


class LandingPage(BasePage):
    # TODO extend once there is more stuff on the landing page
    def navigate(self) -> None:
        self.page.goto(self.domain)


class AllGrantsPage(BasePage):
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="My grants")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/grants")

    def click_set_up_new_grant(self) -> NewGrantPage:
        self.page.get_by_role("button", name="Set up a new grant").click()
        return NewGrantPage(self.page, self.domain)


class FormErrorsMixin(ABC):
    page: Page

    def get_error_title(self, error_title: str) -> Locator:
        return self.page.get_by_role("heading", name=error_title)

    def get_error_subtitle(self, error_message: str) -> Locator:
        return self.page.get_by_role("link", name=error_message)


class NewGrantPage(FormErrorsMixin, BasePage):
    backlink: Locator
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.backlink = self.page.get_by_role("link", name="Back")
        self.title = self.page.get_by_role("heading", name="Set up a new grant")

    T = TypeVar("T", bound=BasePage)

    def complete_grant_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="name").fill(name)

    def submit_new_grant_form(self, expected_response_type: Type[T]) -> T:
        self.page.get_by_role("button", name="Set up grant").click()

        return expected_response_type(self.page, self.domain)


class GrantDashboardBasePage(BasePage):
    dashboard_nav: Locator
    settings_nav: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.dashboard_nav = self.page.get_by_role("link", name="Dashboard")
        self.settings_nav = self.page.get_by_role("link", name="Settings")

    def go_to_dashboard(self) -> GrantDashboardPage:
        self.dashboard_nav.click()
        return GrantDashboardPage(self.page, self.domain)

    def go_to_settings(self) -> GrantSettingsPage:
        self.settings_nav.click()
        return GrantSettingsPage(self.page, self.domain)


class GrantDashboardPage(GrantDashboardBasePage):
    pass


class GrantSettingsPage(GrantDashboardBasePage):
    change_link: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.change_link = self.page.get_by_role("link", name="Change")

    def go_to_change_grant_name(self) -> ChangeGrantNamePage:
        self.change_link.click()
        return ChangeGrantNamePage(self.page, self.domain)


class ChangeGrantNamePage(GrantDashboardBasePage):
    backlink: Locator
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.backlink = self.page.get_by_role("link", name="Back")
        self.title = self.page.get_by_role("heading", name="Grant name")

    T = TypeVar("T", bound=BasePage)

    def complete_grant_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="Grant name").fill(name)

    def submit_change_grant_name_form(self, expected_response_type: Type[T]) -> T:
        self.page.get_by_role("button", name="Change grant name").click()

        return expected_response_type(self.page, self.domain)
