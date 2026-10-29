import logging
from collections.abc import Generator
from logging.handlers import BufferingHandler
from pathlib import Path

import pytest
from flask import Flask

from app.logging.cli_output import ALEMBIC_STDOUT_LOGGER_NAME


@pytest.fixture
def app_log_records(app: Flask) -> Generator[list[logging.LogRecord]]:
    handler = BufferingHandler(capacity=10_000)
    app.logger.addHandler(handler)
    try:
        yield handler.buffer
    finally:
        app.logger.removeHandler(handler)
        for logger_name in ("alembic", ALEMBIC_STDOUT_LOGGER_NAME):
            logging.getLogger(logger_name).removeHandler(handler)


class TestAlembicOutputLogging:
    @pytest.mark.parametrize("args", [["db", "current"], ["db", "heads"]])
    def test_alembic_output_is_logged_through_the_app_handlers_not_printed(
        self, app: Flask, app_log_records: list[logging.LogRecord], args: list[str]
    ) -> None:
        current_revision = Path("app/common/data/migrations/.current-alembic-head").read_text().strip()

        result = app.test_cli_runner().invoke(args=args)

        alembic_records = [record for record in app_log_records if record.name == ALEMBIC_STDOUT_LOGGER_NAME]
        assert result.exit_code == 0, result.output
        assert [record.getMessage() for record in alembic_records] == [f"{current_revision} (head)"]
        assert current_revision not in result.output
