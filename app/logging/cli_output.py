import logging

from flask import current_app
from flask_migrate import Config

from app.logging import route_loggers_through_app

ALEMBIC_STDOUT_LOGGER_NAME = "alembic.stdout"


class LoggingStream:
    """A minimal text stream that logs each complete, non-empty line written to it at INFO on `logger`. Text is
    buffered until a newline, so a line written in several pieces becomes one record; `flush()` logs any unterminated
    remainder."""

    # Alembic encodes text with the stream's encoding (falling back to ascii) before writing it.
    encoding = "utf-8"

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            self._log(line)
        return len(text)

    def flush(self) -> None:
        remainder, self._buffer = self._buffer, ""
        self._log(remainder)

    def _log(self, line: str) -> None:
        if line.strip():
            self.logger.info(line)


def log_alembic_stdout(config: Config) -> Config:
    """Flask-Migrate configure callback: send what Alembic prints (`flask db current`, `heads`, `history`, ...) through
    the application log, because `Config.print_stdout` writes straight to `config.stdout` and bypasses logging.

    The logger is routed through the app's handlers here rather than relying on `env.py`, because commands like
    `flask db heads` never run `env.py`. `config.output_buffer` is deliberately left alone, so `flask db upgrade --sql`
    still writes its SQL to stdout."""
    route_loggers_through_app(current_app, [ALEMBIC_STDOUT_LOGGER_NAME])
    # flask_migrate's stubs don't declare the attributes its Config inherits from alembic's.
    config.stdout = LoggingStream(logging.getLogger(ALEMBIC_STDOUT_LOGGER_NAME))  # ty: ignore[unresolved-attribute]
    return config
