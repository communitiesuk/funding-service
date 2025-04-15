import re
import secrets
from typing import cast

from notifications_python_client import NotificationsAPIClient  # type: ignore[attr-defined]

from tests.e2e.config import EndToEndTestSecrets


def generate_email_address(
    test_name: str,
    email_domain: str = "communities.gov.uk",
) -> str:
    # Help disambiguate tests running around the same time by injecting a random token into the email, so that
    # when we lookup the email it should be unique. We avoid a UUID so as to keep the emails 'short enough'.
    token = secrets.token_urlsafe(8)
    email_address = f"e2e+{test_name}-{token}@{email_domain}".lower()

    return email_address


def extract_email_link(email: dict[str, str]) -> str:
    pattern = r"https?:\/\/[\w-]+(?:\.[\w]+)+(?:[\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])?"

    return cast(str, re.findall(pattern, email["body"])[0])


def retrieve_magic_link(email_address: str, e2e_test_secrets: EndToEndTestSecrets) -> str:
    client = NotificationsAPIClient(e2e_test_secrets.GOVUK_NOTIFY_API_KEY)  # type: ignore[no-untyped-call]

    emails = client.get_all_notifications(template_type="email", status="delivered")["notifications"]  # type: ignore[no-untyped-call]
    for email in emails:
        if email["email_address"] == email_address:
            print(email)
            return extract_email_link(email)

    raise LookupError("Could not find a corresponding find magic link in GOV.UK Notify")
