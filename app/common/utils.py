import re
from typing import Any, Sequence


def slugify(text: str) -> str:
    """
    Convert a string to a URL-friendly slug containing only lowercase alphanumeric characters and hyphens.
    :param text: The string to turn into a slug
    :return: The resulting slug

    For example:
        - "Hello World" -> "hello-world"
        - "Special #$@! Characters" -> "special-characters"
        - "ångström unicode" -> "ngstrm-unicode"
    """
    if not text:
        return ""
    # Remove non-alphanumeric characters except spaces
    text = re.sub(r"[^a-zA-Z0-9\s\-]", "", text)
    # Convert to lowercase

    text = text.lower()
    # Replace spaces (one or more) with a single hyphen
    text = re.sub(r"\s+", "-", text.strip())
    return text


def comma_join_items(items: Sequence[Any], join_word: str = "and") -> str:
    """Take a list of items and join them with commas (sans Oxford) and an optional join word, eg:

    > comma_join_items(["foo", "bar", "baz"]) == "foo, bar and baz"

    > comma_join_items(["foo", "bar", "baz"], join_word="or") == "foo, bar or baz"

    """
    items = list(items)
    if len(items) < 2:
        return "".join(items)
    elif len(items) == 2:
        return f"{items[0]} {join_word} {items[1]}"

    return f"{', '.join(items[:-1])} {join_word} {items[-1]}"
