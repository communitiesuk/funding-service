from datetime import date, datetime


def format_date(value: date | datetime) -> str:
    """Format a date or datetime as follows:

    > Friday 16 May 2025
    """
    return value.strftime("%A %-d %B %-Y")


def format_date_short(value: date | datetime) -> str:
    """Format a date or datetime as follows:

    > 16 May 2025
    """
    return value.strftime("%-d %B %-Y")


def format_datetime(value: datetime) -> str:
    """Format a datetime as follows:

    > 10:37am on Friday 16 May 2025

    If the datetime is exactly on the hour, then minutes will not be included:

    > 10am on Friday 16 May 2025
    """
    fmt = "%-I:%M%p on %A %-d %B %-Y"

    if value.minute == 0:
        fmt = "%-I%p on %A %-d %B %-Y"

    formatted_datetime = value.strftime(fmt)
    formatted_datetime = formatted_datetime.replace("AM", "am").replace("PM", "pm")

    return formatted_datetime


def format_date_range(start: date, end: date) -> str:
    """Format a pair of dates as follows:

    > Wednesday 1 January 2025 to Saturday 1 February 2025
    """
    from_, to = format_date(start), format_date(end)
    return f"{from_} to {to}"


def format_datetime_range(start: datetime, end: datetime) -> str:
    """Format a pair of dates as follows:

    > 9:15am on Wednesday 1 January 2025 to 5:45pm on Saturday 1 February 2025

    As with `format_datetime`, if the times are exactly on the hour then minutes will not be included:

    > 9am on Wednesday 1 January 2025 to 5pm on Saturday 1 February 2025
    """
    from_, to = format_datetime(start), format_datetime(end)
    return f"{from_} to {to}"
