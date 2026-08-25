from typing import overload


@overload
def strip_string_if_not_empty(value: None) -> None: ...
@overload
def strip_string_if_not_empty[T: str](value: T) -> T: ...
def strip_string_if_not_empty(value: str | None) -> str | None:
    if value is None:
        return None

    if not value:
        return value

    # Keep it working with str subclasses like ExpressionStatement; we should return the same type
    stripped = value.strip()
    if type(value) is not str:
        return type(value)(stripped)

    return stripped
