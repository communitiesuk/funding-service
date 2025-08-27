from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Locator, Page, expect

if TYPE_CHECKING:
    from tests.e2e.pages import AllGrantsPage


class GrantDevelopersBasePage:
    domain: str
    page: Page

    heading: Locator
    grant_name: str

    def __init__(self, page: Page, domain: str, heading: Locator, grant_name: str) -> None:
        self.page = page
        self.domain = domain
        self.heading = heading
        self.grant_name = grant_name


class GrantDevelopersPage(GrantDevelopersBasePage):
    manage_collections_link: Locator
    delete_link: Locator
    confirm_delete: Locator
    add_collection_button: Locator
    summary_row_submissions: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} Developers")
        )
        self.manage_collections_link = self.page.get_by_role("link", name="Manage")
        self.delete_link = page.get_by_role("link", name="Delete this grant")
        self.confirm_delete = page.get_by_role("button", name="Confirm deletion")
        self.add_collection_button = self.page.get_by_role("button", name="Add a monitoring report").or_(
            self.page.get_by_role("button", name="Add another monitoring report")
        )
        self.summary_row_submissions = page.locator("div.govuk-summary-list__row").filter(
            has=page.get_by_text("Submissions")
        )

    def delete_grant(self) -> "AllGrantsPage":
        from tests.e2e.pages import AllGrantsPage

        self.delete_link.click()
        self.confirm_delete.click()
        all_grants_page = AllGrantsPage(self.page, self.domain)
        expect(all_grants_page.title).to_be_visible()
        return all_grants_page
