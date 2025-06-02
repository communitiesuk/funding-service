import uuid

import pytest
from playwright.sync_api import Page

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.pages import AllGrantsPage


def create_grant(grant_name: str, page: Page, domain: str) -> None:
    """
    Split this out as a separate function for now while we decide if we want this test to create the grant it uses,
    or whether we go with a different option
    (See notes in ticket FSPT-441)
    :param grant_name: name of grant to create
    :param page: page object from Playwright
    :param domain: domain to use for the test
    :return:
    """
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # Set up new grant
    new_grant_page = all_grants_page.click_set_up_new_grant()
    new_grant_page.fill_in_grant_name(grant_name)
    all_grants_page = new_grant_page.click_submit()
    all_grants_page.check_grant_exists(grant_name)


@pytest.mark.skip_in_environments(["dev", "test", "prod"])
def test_create_and_preview_schema(domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: Page):
    # TODO - FSPT-441: Decide if we want to create the grant in this test or not.
    new_grant_name = f"E2E schema {uuid.uuid4()}"
    create_grant(new_grant_name, authenticated_browser_sso, domain)

    # Go to Grant Dashboard
    all_grants_page = AllGrantsPage(authenticated_browser_sso, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(new_grant_name)

    # Go to developers tab
    developers_page = grant_dashboard_page.click_developers(new_grant_name)
    assert developers_page is not None
