import datetime
import json
import urllib.request

from cachetools.func import ttl_cache


@ttl_cache(maxsize=1, ttl=60 * 60 * 24)  # Cache in memory for 24 hours
def get_bank_holidays() -> frozenset[datetime.date]:
    """Fetch UK (England and Wales) bank holidays, cached for 24h."""
    try:
        with urllib.request.urlopen("https://www.gov.uk/bank-holidays.json", timeout=5) as resp:
            data = json.loads(resp.read())
        return frozenset(datetime.date.fromisoformat(event["date"]) for event in data["england-and-wales"]["events"])
    except OSError, KeyError, ValueError:
        return frozenset()


def subtract_business_days(from_date: datetime.date, days: int) -> datetime.date:
    """Subtract N business days from a date, skipping weekends and UK bank holidays."""
    bank_holidays = get_bank_holidays()
    result = from_date
    remaining = days
    while remaining > 0:
        result -= datetime.timedelta(days=1)
        if result.weekday() < 5 and result not in bank_holidays:
            remaining -= 1
    return result
