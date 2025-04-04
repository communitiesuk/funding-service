from __future__ import annotations

from abc import ABC, abstractmethod
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
    def get_title(self) -> Locator:
        return self.page.get_by_role("heading", name="All grants")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/grants")

    def click_set_up_new_grant(self) -> NewGrantPage:
        self.page.get_by_role("button", name="Set up a new grant").click()
        return NewGrantPage(self.page, self.domain)


class NewGrantErrorPage(ABC, BasePage):
    def get_error_title(self) -> Locator:
        return self.page.get_by_role("heading", name="There is a problem")

    @abstractmethod
    def get_error_subtitle(self) -> Locator:
        pass


class NewGrantPage(BasePage):
    def complete_grant_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="name").fill(name)

    T = TypeVar("T", bound=BasePage)

    def submit_new_grant_form(self, expected_response_type: Type[T]) -> T:
        self.page.get_by_role("button", name="Submit").click()

        return expected_response_type(self.page, self.domain)


class NewGrantDuplicateNameErrorPage(NewGrantErrorPage):
    def get_error_subtitle(self) -> Locator:
        return self.page.get_by_role("link", name="Grant name already in use")


class NewGrantIncompleteErrorPage(NewGrantErrorPage):
    def get_error_subtitle(self) -> Locator:
        return self.page.get_by_role("link", name="This field is required.")
