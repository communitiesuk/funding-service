import re
from typing import TYPE_CHECKING, Any, Sequence

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import inspect

if TYPE_CHECKING:
    from app.common.data.base import BaseModel


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


def uppercase_first(text: str | None) -> str | None:
    if not text:
        return text

    return text[0].upper() + text[1:]


def to_dict(instance: BaseModel, exclude: list[str] | None = None) -> dict[str, Any]:
    return {
        prop.key: (field.model_dump(mode="json", exclude_none=True) if isinstance(field, PydanticBaseModel) else field)
        for prop in inspect(instance.__class__).column_attrs
        if (field := getattr(instance, prop.key)) is not None
        and prop.columns[0].name not in {"created_at_utc", "updated_at_utc"}
        and not prop.key.startswith("_")
        and (exclude is None or prop.key not in exclude)
    }
