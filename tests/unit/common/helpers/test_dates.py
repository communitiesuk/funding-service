import datetime
from unittest.mock import patch

import pytest

from app.common.helpers.dates import subtract_business_days


@pytest.fixture(autouse=True)
def mock_bank_holidays():
    with patch(
        "app.common.helpers.dates.get_bank_holidays",
        return_value=frozenset(
            {
                datetime.date(2026, 12, 25),
                datetime.date(2026, 12, 28),
                datetime.date(2026, 6, 22),
            }
        ),
    ):
        yield


class TestSubtractBusinessDays:
    def test_simple_weekdays(self):
        friday = datetime.date(2026, 6, 19)
        result = subtract_business_days(friday, 3)
        assert result == datetime.date(2026, 6, 16)

    def test_skips_weekends(self):
        monday = datetime.date(2026, 6, 22)
        result = subtract_business_days(monday, 1)
        assert result == datetime.date(2026, 6, 19)

    def test_skips_bank_holidays(self):
        day_after_bank_holiday = datetime.date(2026, 6, 23)
        result = subtract_business_days(day_after_bank_holiday, 1)
        assert result == datetime.date(2026, 6, 19)

    def test_skips_bank_holiday_and_weekend(self):
        tuesday_after_xmas = datetime.date(2026, 12, 30)
        result = subtract_business_days(tuesday_after_xmas, 2)
        assert result == datetime.date(2026, 12, 24)

    def test_zero_days_returns_same_date(self):
        date = datetime.date(2026, 6, 18)
        result = subtract_business_days(date, 0)
        assert result == date

    def test_five_business_days(self):
        friday = datetime.date(2026, 6, 26)
        result = subtract_business_days(friday, 5)
        assert result == datetime.date(2026, 6, 18)
