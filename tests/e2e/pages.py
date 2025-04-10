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
    T = TypeVar("T", bound=BasePage)

    def complete_grant_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="name").fill(name)

    def submit_new_grant_form(self, expected_response_type: Type[T]) -> T:
        self.page.get_by_role("button", name="Set up grant").click()

        return expected_response_type(self.page, self.domain)
