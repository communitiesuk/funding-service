import datetime
import logging
import time
from collections.abc import Iterable
from logging import LogRecord
from logging.config import dictConfig
from typing import TYPE_CHECKING, Any, cast

from flask import Flask, Response, g, request, session
from flask_login import user_loaded_from_cookie, user_logged_in, user_logged_out
from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.json import JsonFormatter as BaseJSONFormatter

from app.logging import correlation
from app.logging.correlation import (
    CORRELATION_RECORD_ATTR,
    SCALAR_LOG_VALUE_TYPES,
    ContextType,
    get_record_correlation,
)

if TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse, WSGIApplication, WSGIEnvironment

request_logger = logging.getLogger("app.request")

# Flat, snake_case names: CloudWatch Logs Insights discovers top-level JSON keys automatically, and keys without dots or
# hyphens can be used in `filter`/`stats`/`display` without backtick-quoting.
JSON_RENAME_FIELDS = {
    "levelname": "level",
    "name": "logger",
    "funcName": "function",
    "pathname": "file",
    "lineno": "line",
}
JSON_FORMAT = "%(levelname)s %(name)s %(message)s %(funcName)s %(pathname)s %(lineno)d %(process)d"
PLAINTEXT_FORMAT = "%(asctime)s %(levelname)s - %(message)s - from %(funcName)s() in %(filename)s:%(lineno)d"


def get_default_logging_config(app: Flask) -> dict[str, Any]:
    log_level = app.config["LOG_LEVEL"]
    formatter = app.config["LOG_FORMATTER"]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "reject_mutable_data_structures": {
                "()": "app.logging.RejectMutableDataStructuresFilter",
            },
        },
        "formatters": {
            "plaintext": {
                "()": "app.logging.PlaintextFormatter",
                "fmt": PLAINTEXT_FORMAT,
                "full_context": False,
            },
            "plaintext-full": {
                "()": "app.logging.PlaintextFormatter",
                "fmt": PLAINTEXT_FORMAT,
                "full_context": True,
            },
            "json": {
                "()": "app.logging.JSONFormatter",
                "fmt": JSON_FORMAT,
            },
        },
        "handlers": {
            "null": {
                "class": "logging.NullHandler",
            },
            "sentry": {
                "class": "sentry_sdk.integrations.logging.SentryLogsHandler",
                # Correlation fields reach Sentry Logs as isolation-scope attributes (see `app.logging.correlation`),
                # not through a formatter: SentryLogsHandler reads the message template and record extras directly.
            },
            "default": {
                "filters": ["reject_mutable_data_structures"],
                "formatter": formatter,
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["null"],
            },
            "werkzeug": {
                "disabled": True,
            },
            app.name: {
                "handlers": ["default", "sentry"],
                "level": log_level,
            },
        },
    }


def init_app(app: Flask, log_config: dict[str, Any] | None = None) -> None:
    correlation.install_log_record_factory()
    log_config = log_config or get_default_logging_config(app)
    dictConfig(log_config)

    app.wsgi_app = CorrelationMiddleware(app, app.wsgi_app)  # ty: ignore[invalid-assignment]
    attach_request_loggers(app)

    user_logged_in.connect(_bind_logged_in_user, app)
    user_loaded_from_cookie.connect(_bind_logged_in_user, app)
    user_logged_out.connect(_unbind_logged_out_user, app)


def route_loggers_through_app(app: Flask, logger_names: Iterable[str], level: int = logging.INFO) -> None:
    """Send third-party loggers (eg alembic during `flask db upgrade`) through the app's handlers, so that their lines
    share the application's format and correlation fields."""
    for name in logger_names:
        third_party_logger = logging.getLogger(name)
        third_party_logger.handlers = list(app.logger.handlers)
        third_party_logger.setLevel(level)
        third_party_logger.propagate = False
        third_party_logger.disabled = False


class CorrelationMiddleware:
    """Wraps `Flask.wsgi_app`, so it runs inside Sentry's WSGI middleware (which forks the Sentry scope and continues
    the trace) and around everything Flask does for the request, including error handlers and teardown.

    It enters the request's unit of work, which every line logged while Flask handles the request is correlated with."""

    def __init__(self, app: Flask, wsgi_app: WSGIApplication) -> None:
        self.app = app
        self.wsgi_app = wsgi_app

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
        with correlation.request_context(
            environ,
            alb_trace_id=correlation.parse_alb_trace_id(environ.get("HTTP_X_AMZN_TRACE_ID")),
            cloudfront_request_id=correlation.parse_cloudfront_request_id(environ.get("HTTP_X_AMZ_CF_ID")),
            debug_logging=False,
        ):
            return self.wsgi_app(environ, start_response)


def attach_request_loggers(app: Flask) -> None:
    @app.before_request
    def bind_request_and_log_start() -> None:
        # annotating this onto request instead of flask.g as it probably shouldn't be inheritable from a request-less
        # application context
        request.before_request_real_time = time.perf_counter()  # ty: ignore[unresolved-attribute]

        correlation.bind(
            method=request.method,
            path=request.path,
            endpoint=request.endpoint,
            user_id=_current_user_id(),
        )
        if request.path != "/healthcheck":
            request_logger.info("Request started %(method)s %(path)s", {"method": request.method, "path": request.path})

    @app.after_request
    def log_request_finished(response: Response) -> Response:
        if request.path != "/healthcheck":
            duration_ms = (
                round((time.perf_counter() - cast(float, request.before_request_real_time)) * 1000, 2)
                if hasattr(request, "before_request_real_time")
                else None
            )
            status = response.status_code
            request_logger.info(
                "Request finished %(method)s %(path)s %(status)s in %(duration_ms)sms",
                {"method": request.method, "path": request.path, "status": status, "duration_ms": duration_ms},
                extra={"status": status, "duration_ms": duration_ms},
            )
        return response


def _current_user_id() -> str | None:
    # Use the user Flask-Login has already loaded for this app context, if any; otherwise read Flask-Login's user id
    # from the (signed) session, so that we never hit the database just to produce a log line.
    if "_login_user" in g:
        user = g._login_user
        return correlation.as_uuid_str(user.get_id()) if user.is_authenticated else None
    return correlation.as_uuid_str(session.get("_user_id"))


def _bind_logged_in_user(sender: Flask, user: Any, **kwargs: Any) -> None:
    correlation.bind(user_id=correlation.as_uuid_str(user.get_id()))


def _unbind_logged_out_user(sender: Flask, **kwargs: Any) -> None:
    correlation.bind(user_id=None)


class RejectMutableDataStructuresFilter(logging.Filter):
    def filter(self, record: LogRecord) -> LogRecord:
        # The policy applies to our own code. Third-party loggers routed through the app's handlers (eg alembic during
        # `flask db upgrade`) use positional args with their own objects, and must not be able to break a migration.
        if record.name != "app" and not record.name.startswith("app."):
            return record

        logging_msg_args: dict[str, Any] | None
        if isinstance(record.args, tuple):
            logging_msg_args = record.args[0] if len(record.args) > 0 else None  # ty: ignore[invalid-assignment]
        else:
            logging_msg_args = record.args  # ty: ignore[invalid-assignment]

        if not logging_msg_args:
            return record

        for _k, v in logging_msg_args.items():
            if not isinstance(v, SCALAR_LOG_VALUE_TYPES):
                # We want to only allow basic data types to be logged. There is a security/data protection risk that
                # comes with logging more complex types like lists and dicts; it is easier to accidentally include
                # PII, or to make a change in the future that adds it without realising we'll end up logging it out.
                raise ValueError(f"Attempt to log data type `{type(v)}` rejected by security policy.")
        return record


class JSONFormatter(BaseJSONFormatter):
    """One flat JSON object per line. Correlation fields are written last, so they win over any `extra=` key of the
    same name, whether from our own code or from third-party loggers routed through the app's handlers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not args:
            kwargs.setdefault("fmt", JSON_FORMAT)
        kwargs.setdefault("rename_fields", JSON_RENAME_FIELDS)
        kwargs.setdefault("static_fields", {"log_type": "application"})
        kwargs.setdefault("timestamp", True)
        kwargs.setdefault("reserved_attrs", [*RESERVED_ATTRS, CORRELATION_RECORD_ATTR])
        super().__init__(*args, **kwargs)

    def add_fields(self, log_data: dict[str, Any], record: LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_data, record, message_dict)
        # Under gevent's monkey-patching this is the greenlet's identity. Stringified because it can exceed the range
        # of integers that JSON consumers represent exactly.
        log_data["thread"] = str(record.thread)
        if task_name := getattr(record, "taskName", None):
            log_data["task_name"] = task_name
        log_data.update(get_record_correlation(record))


class PlaintextFormatter(logging.Formatter):
    """Human-readable local format. By default (`LOG_FORMATTER=plaintext`) a line in a request ends with a short tag,
    the first 8 characters of its `request_id`, so the lines of one request can be told apart. With `full_context`
    (`LOG_FORMATTER=plaintext-full`) every correlation field is appended instead, so behaviour can be verified
    locally."""

    def __init__(self, *args: Any, full_context: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.full_context = full_context

    def formatTime(self, record: LogRecord, datefmt: str | None = None) -> str:
        return datetime.datetime.fromtimestamp(record.created, datetime.UTC).isoformat(timespec="milliseconds")

    def formatMessage(self, record: LogRecord) -> str:
        line = super().formatMessage(record)
        fields = get_record_correlation(record)
        if not fields:
            return line
        if self.full_context:
            return f"{line} [{' '.join(f'{key}={value}' for key, value in fields.items())}]"
        tag = next((fields[key] for key in ("request_id",) if key in fields), None)
        if tag is None:
            return line
        return f"{line} [{str(tag)[:8]}]"


__all__ = [
    "ContextType",
    "CorrelationMiddleware",
    "JSONFormatter",
    "PlaintextFormatter",
    "RejectMutableDataStructuresFilter",
    "correlation",
    "get_default_logging_config",
    "init_app",
    "route_loggers_through_app",
]
