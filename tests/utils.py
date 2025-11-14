import json
import re
from functools import lru_cache
from re import Pattern
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, cast

from bs4 import BeautifulSoup, Tag
from flask_wtf import FlaskForm
from testcontainers.postgres import PostgresContainer


def page_has_error(soup: BeautifulSoup, message: str) -> bool:
    error_summary = soup.find("div", class_="govuk-error-summary")
    if not error_summary:
        return False

    error_messages = error_summary.select("li a")
    return any(message in error_message.text for error_message in error_messages)


class RestrictedAny:
    """
    Analogous to mock.ANY, this class takes an arbitrary callable in its constructor and the returned instance will
    appear to "equal" anything that produces a truthy result when passed as an argument to the ``condition`` callable.

    Useful when wanting to assert the contents of a larger structure but be more flexible for certain members, e.g.

    # only care that second number is odd
    >>> (4, 5, 6,) == (4, RestrictedAny(lambda x: x % 2), 6,)
    True
    >>> (4, 9, 6,) == (4, RestrictedAny(lambda x: x % 2), 6,)
    True
    """

    def __init__(self, condition: Callable[[Any], bool]) -> None:
        self._condition = condition

    def __eq__(self, other: Any) -> bool:
        return self._condition(other)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._condition})"

    def __hash__(self) -> None:  # type: ignore[override]
        return None


class AnySupersetOf(RestrictedAny):
    """
    Instance will appear to "equal" any dictionary-like object that is a "superset" of the the constructor-supplied
    ``subset_dict``, i.e. will ignore any keys present in the dictionary in question but missing from the reference
    dict. e.g.

    >>> [{"a": 123, "b": 456, "less": "predictabananas"}, 789] == [AnySupersetOf({"a": 123, "b": 456}), 789]
    True
    """

    def __init__(self, subset_dict: Mapping[str, Any]) -> None:
        # take an immutable dict copy of supplied dict-like object
        self._subset_dict = MappingProxyType(dict(subset_dict))

    def _condition(self, other: Any) -> bool:
        return self._subset_dict == {k: v for k, v in other.items() if k in self._subset_dict}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._subset_dict})"


class AnyStringMatching(RestrictedAny):
    """
    Instance will appear to "equal" any string that matches the constructor-supplied regex pattern

    >>> {"a": "Metempsychosis", "b": "c"} == {"a": AnyStringMatching(r"m+.+psycho.*", flags=re.I), "b": "c"}
    True
    """

    _cached_re_compile = staticmethod(lru_cache(maxsize=32)(re.compile))

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """
        Construct an instance which will equal any string matching the supplied regex pattern. Supports all arguments
        recognized by ``re.compile``, alternatively accepts an existing regex pattern object as a single argument.
        """
        self._regex = (
            args[0] if len(args) == 1 and isinstance(args[0], Pattern) else self._cached_re_compile(*args, **kwargs)
        )
        super().__init__(lambda other: isinstance(other, str | bytes) and bool(self._regex.match(other)))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._regex})"


def build_db_config(setup_db_container: PostgresContainer | None) -> Dict[str, Any]:
    if setup_db_container is None:
        return {
            "DATABASE_HOST": "localhost",
            "DATABASE_PORT": "5432",
            "DATABASE_NAME": "db-access-not-available-for-unit-tests",
            # pragma: allowlist nextline secret
            "DATABASE_SECRET": json.dumps({"username": "invalid", "password": "invalid"}),
            "DEBUG_TB_ENABLED": "false",
        }
    return {
        "DATABASE_HOST": setup_db_container.get_container_host_ip(),
        "DATABASE_PORT": str(setup_db_container.get_exposed_port(5432)),
        "DATABASE_NAME": setup_db_container.dbname,
        "DATABASE_SECRET": json.dumps(
            {"username": setup_db_container.username, "password": setup_db_container.password}
        ),
        "DEBUG_TB_ENABLED": "false",
    }


def get_soup_text(soup: BeautifulSoup, tag: str) -> str:
    element = getattr(soup, tag)
    assert element, f"Could not find <{tag}> on page"
    return re.sub(r"\s+", " ", cast(str, element.text).strip())


def get_h1_text(soup: BeautifulSoup) -> str:
    return get_soup_text(soup, "h1")


def get_h2_text(soup: BeautifulSoup) -> str:
    return get_soup_text(soup, "h2")


def page_has_link(soup: BeautifulSoup, link_text: str) -> Tag | None:
    links = soup.select("a")

    for link in links:
        if link_text in link.text:
            return link

    return None


def page_has_button(soup: BeautifulSoup, button_text: str) -> Tag | None:
    buttons = soup.select("button")

    for button in buttons:
        if button_text in button.text:
            return button

    return None


def page_has_flash(soup: BeautifulSoup, flash_text: str) -> Tag | None:
    flash_messages = soup.find_all(class_="govuk-notification-banner__content")

    for flash_message in flash_messages:
        if flash_text in flash_message.text:
            return flash_message

    return None


def get_form_data(form: FlaskForm, submit: str = "y") -> dict[str, Any]:
    """Get the data from a flask form suitable for passing as `data` to a Flask test client's `post` method.

    Specifically we need to strip out any null/falsey data, which can be stringified into eg `"False"` and ends up
    being processed as "truthy".
    """
    data = {k: v for k, v in form.data.items() if v}

    # If we're getting the form data, we want to submit the form
    if hasattr(form, "submit") and submit:
        data["submit"] = "y"

    return data
