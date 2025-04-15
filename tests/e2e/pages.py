from __future__ import annotations

from abc import ABC

from playwright.sync_api import Locator, Page, expect


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


class AllGrantsPage(TopNavMixin, BasePage):
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="My grants")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/grants")
        expect(self.title).to_be_visible()

    def click_set_up_new_grant(self) -> NewGrantPage:
        self.page.get_by_role("button", name="Set up a new grant").click()
        new_grant_page = NewGrantPage(self.page, self.domain)
        expect(new_grant_page.title).to_be_visible()
        return new_grant_page

    def check_grant_exists(self, grant_name: str) -> None:
        expect(self.page.get_by_role("link", name=grant_name)).to_be_visible()

    def check_grant_doesnt_exist(self, grant_name: str) -> None:
        expect(self.page.get_by_role("link", name=grant_name, exact=True)).not_to_be_visible()

    def click_grant(self, grant_name: str) -> GrantDashboardPage:
        self.page.get_by_role("link", name=grant_name).click()
        grant_dashboard_page = GrantDashboardPage(self.page, self.domain)
        expect(self.page.get_by_role("heading", name=grant_name)).to_be_visible()
        return grant_dashboard_page


class NewGrantPage(TopNavMixin, BasePage):
    backlink: Locator
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.backlink = self.page.get_by_role("link", name="Back")
        self.title = self.page.get_by_role("heading", name="Set up a new grant")

    def fill_in_grant_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="name").fill(name)

    def click_submit(self) -> AllGrantsPage:
        self.page.get_by_role("button", name="Set up grant").click()
        all_grants_page = AllGrantsPage(self.page, self.domain)
        expect(all_grants_page.title).to_be_visible()
        return all_grants_page


class GrantDashboardBasePage(TopNavMixin, BasePage):
    dashboard_nav: Locator
    settings_nav: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.dashboard_nav = self.page.get_by_role("link", name="Dashboard")
        self.settings_nav = self.page.get_by_role("link", name="Settings")

    def click_dashboard(self) -> GrantDashboardPage:
        self.dashboard_nav.click()
        return GrantDashboardPage(self.page, self.domain)

    def click_settings(self, grant_name: str) -> GrantSettingsPage:
        self.settings_nav.click()
        grant_settings_page = GrantSettingsPage(self.page, self.domain)
        expect(grant_settings_page.page.get_by_role("heading", name=f"{grant_name} Settings")).to_be_visible()
        return grant_settings_page


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
