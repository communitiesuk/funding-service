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
