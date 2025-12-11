import re
from typing import cast
from urllib.parse import urlencode

from notifications_python_client import NotificationsAPIClient  # type: ignore[attr-defined]
from playwright.sync_api import Page

from tests.e2e.config import EndToEndTestSecrets


def extract_email_link(email: dict[str, str]) -> str:
    pattern = r"https?:\/\/[\w-]+(?:\.[\w]+)+(?:[\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])?"

    return cast(str, re.findall(pattern, email["body"])[0])


def retrieve_magic_link(notification_id: str, e2e_test_secrets: EndToEndTestSecrets) -> str:
    client = NotificationsAPIClient(e2e_test_secrets.GOVUK_NOTIFY_API_KEY)  # type: ignore[no-untyped-call]
    email = client.get_notification_by_id(notification_id)  # type: ignore[no-untyped-call]

    if not email:
        raise LookupError("Could not find a corresponding find magic link in GOV.UK Notify")

    return extract_email_link(email)


def delete_grant_through_admin(page: Page, domain: str, search: str) -> None:
    query = urlencode(query=dict(search=search))
    page.goto(f"{domain}/deliver/admin/grant/?{query}")

    assert len(page.get_by_role("link", name=re.compile(search)).all()) == 1

    page.check("#select-all")
    page.locator("button:has-text('Delete (1 selected)')").click()
    page.locator("button:has-text('Confirm delete')").click()
