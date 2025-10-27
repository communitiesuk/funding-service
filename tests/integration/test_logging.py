import datetime
from typing import Any

import pytest


class TestLogging:
    def test_basic_log_message(self, app, caplog) -> None:
        with app.app_context():
            app.logger.info("this is a test log message")

        assert caplog.messages == ["this is a test log message"]

    @pytest.mark.parametrize("simple", ["hello", 1, 1.0, True])
    def test_can_log_simple_interpolated_values(self, app, caplog, simple: Any) -> None:
        with app.app_context():
            app.logger.info("this is a test log %(simple)s", {"simple": simple})

        assert caplog.messages == [f"this is a test log {simple}"]

    @pytest.mark.parametrize("complex", [[1, 2, 3], (1, 2, 3), {"a": "b"}, {"a"}])
    def test_cannot_log_complex_data_types(self, app, caplog, complex: Any) -> None:
        with app.app_context(), pytest.raises(ValueError) as exc:
            app.logger.info("this is a test log %(complex)s", {"complex": complex})

        assert isinstance(exc.value, ValueError)
        assert str(exc.value) == f"Attempt to log data type `{type(complex)}` rejected by security policy."

    def test_can_log_date(self, app, caplog) -> None:
        test_date = datetime.date(2023, 6, 30)
        with app.app_context():
            app.logger.info("this is a test log %(date)s", {"date": test_date})

        assert caplog.messages == ["this is a test log 2023-06-30"]

    def test_can_log_datetime(self, app, caplog) -> None:
        test_datetime = datetime.datetime(2023, 6, 30, 14, 30, 45)
        with app.app_context():
            app.logger.info("this is a test log %(datetime)s", {"datetime": test_datetime})

        assert caplog.messages == ["this is a test log 2023-06-30 14:30:45"]
