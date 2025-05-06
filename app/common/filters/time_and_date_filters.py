from datetime import datetime

from babel import dates


def format_date(value: datetime) -> str:
    return dates.format_date(value, "dd MMM YYYY")
