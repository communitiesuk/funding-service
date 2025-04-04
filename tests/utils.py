from typing import cast

from bs4 import BeautifulSoup, Tag


def page_has_error(soup: BeautifulSoup, message: str) -> bool:
    error_summary = cast(Tag | None, soup.find("div", class_="govuk-error-summary"))
    if not error_summary:
        return False

    error_messages = error_summary.select("li a")
    return any(message in error_message.text for error_message in error_messages)
