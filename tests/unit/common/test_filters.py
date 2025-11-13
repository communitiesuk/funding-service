import datetime

from app import format_date, format_date_range, format_datetime, format_datetime_range
from app.common.filters import format_date_range_short


class TestFormatDate:
    def test_date(self):
        assert format_date(datetime.date(2025, 1, 1)) == "Wednesday 1 January 2025"

    def test_datetime(self):
        assert format_date(datetime.datetime(2025, 1, 1, 12, 0, 0)) == "Wednesday 1 January 2025"


class TestFormatDatetime:
    def test_datetime_am(self):
        assert format_datetime(datetime.datetime(2025, 1, 1, 1, 0, 0)) == "1am on Wednesday 1 January 2025"

    def test_datetime_pm(self):
        assert format_datetime(datetime.datetime(2025, 1, 1, 13, 0, 0)) == "1pm on Wednesday 1 January 2025"

    def test_datetime_minutes(self):
        assert format_datetime(datetime.datetime(2025, 1, 1, 13, 37, 0)) == "1:37pm on Wednesday 1 January 2025"

    def test_datetime_noon(self):
        assert format_datetime(datetime.datetime(2025, 1, 1, 12, 0, 0)) == "12pm on Wednesday 1 January 2025"

    def test_datetime_midnight(self):
        assert format_datetime(datetime.datetime(2025, 1, 1, 0, 0, 0)) == "12am on Wednesday 1 January 2025"


class TestFormatDateRange:
    def test_dates(self):
        assert (
            format_date_range(datetime.date(2025, 1, 1), datetime.date(2025, 2, 1))
            == "Wednesday 1 January 2025 to Saturday 1 February 2025"
        )


class TestFormatDateRangeShort:
    def test_dates(self):
        assert (
            format_date_range_short(datetime.date(2025, 1, 1), datetime.date(2025, 2, 1))
            == "1 January 2025 to 1 February 2025"
        )


class TestFormatDatetimeRange:
    def test_datetimes(self):
        assert (
            format_datetime_range(datetime.datetime(2025, 1, 1, 9, 0, 0), datetime.datetime(2025, 2, 1, 17, 0, 0))
            == "9am on Wednesday 1 January 2025 to 5pm on Saturday 1 February 2025"
        )

    def test_datetimes_minutes(self):
        assert (
            format_datetime_range(datetime.datetime(2025, 1, 1, 9, 15, 0), datetime.datetime(2025, 2, 1, 17, 45, 0))
            == "9:15am on Wednesday 1 January 2025 to 5:45pm on Saturday 1 February 2025"
        )
