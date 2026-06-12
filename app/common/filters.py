import decimal
from datetime import UTC, date, datetime
from typing import cast
from zoneinfo import ZoneInfo

from num2words import num2words

DEFAULT_DISPLAY_TZ = ZoneInfo("Europe/London")


def _coerce_tz[T: date | datetime](value: T, tz: ZoneInfo | None) -> T:
    if tz is None or not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)  # ty: ignore[invalid-assignment]

    return cast(T, value.astimezone(tz))  # ty: ignore[unresolved-attribute]


def format_date(value: date | datetime, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a date or datetime as follows:

    > Friday 16 May 2025
    """
    return _coerce_tz(value, tz).strftime("%A %-d %B %-Y")


def format_date_short(value: date | datetime, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a date or datetime as follows:

    > 16 May 2025
    """
    return _coerce_tz(value, tz).strftime("%-d %B %-Y")


def format_date_approximate(value: date | datetime, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a date or datetime as follows:

    > May 2025
    """
    return _coerce_tz(value, tz).strftime("%B %-Y")


def format_datetime(value: datetime, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a datetime as follows:

    > 10:37am on Friday 16 May 2025

    If the datetime is exactly on the hour, then minutes will not be included:

    > 10am on Friday 16 May 2025
    """
    value = _coerce_tz(value, tz)
    fmt = "%-I:%M%p on %A %-d %B %-Y"

    if value.minute == 0:
        fmt = "%-I%p on %A %-d %B %-Y"

    formatted_datetime = value.strftime(fmt)
    formatted_datetime = formatted_datetime.replace("AM", "am").replace("PM", "pm")

    return formatted_datetime


def format_datetime_short(value: datetime, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a datetime as follows:

    > 22 Feb 2026 at 3:41pm

    If the datetime is exactly on the hour, then minutes will not be included:

    > 22 Feb 2026 at 3pm
    """
    value = _coerce_tz(value, tz)
    fmt = "%-d %b %-Y at %-I:%M%p"

    if value.minute == 0:
        fmt = "%-d %b %-Y at %-I%p"

    formatted_datetime = value.strftime(fmt)
    formatted_datetime = formatted_datetime.replace("AM", "am").replace("PM", "pm")

    return formatted_datetime


def format_date_range(start: date, end: date, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a pair of dates as follows:

    > Wednesday 1 January 2025 to Saturday 1 February 2025
    """
    from_, to = format_date(start, tz=tz), format_date(end, tz=tz)
    return f"{from_} to {to}"


def format_date_range_short(start: date, end: date, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a pair of dates as follows:

    > 1 January 2025 to 1 February 2025
    """
    from_, to = format_date_short(start, tz=tz), format_date_short(end, tz=tz)
    return f"{from_} to {to}"


def format_datetime_range(start: datetime, end: datetime, tz: ZoneInfo | None = DEFAULT_DISPLAY_TZ) -> str:
    """Format a pair of dates as follows:

    > 9:15am on Wednesday 1 January 2025 to 5:45pm on Saturday 1 February 2025

    As with `format_datetime`, if the times are exactly on the hour then minutes will not be included:

    > 9am on Wednesday 1 January 2025 to 5pm on Saturday 1 February 2025
    """
    from_, to = format_datetime(start, tz=tz), format_datetime(end, tz=tz)
    return f"{from_} to {to}"


def iso_utc(value: datetime) -> str:
    """Render a datetime as an ISO 8601 string with an explicit UTC offset.

    Naive datetimes are assumed to be UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def to_ordinal(number: int) -> str:
    return cast(str, num2words(number, to="ordinal"))


def format_thousands(number: int | decimal.Decimal) -> str:
    return f"{number:,}"
