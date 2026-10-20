import datetime
import ipaddress
import logging
import time
from collections.abc import Iterable, Iterator
from contextlib import ExitStack
from logging import LogRecord
from logging.config import dictConfig
from typing import TYPE_CHECKING, Any

from flask import Flask, g, request, session
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
from app.logging.unlogged import is_unlogged_path

if TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse, WSGIApplication, WSGIEnvironment

_MAX_USER_AGENT_LENGTH = 256

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

    It enters the request's unit of work and logs the single "Request finished" line per response. That line is logged
    here rather than in `after_request` so that it is also emitted when an exception propagates out of Flask (eg
    `PROPAGATE_EXCEPTIONS` in debug mode). For a streamed response (one without a Content-Length header) it also logs a
    DEBUG "Response streaming" line when the headers are sent, before the body is generated.

    The unit of work stays entered until the WSGI server closes the response iterable, which it does after sending the
    whole body (gunicorn, werkzeug's dev server and its test client all do). So lines logged while a streamed response
    body is generated (eg `stream_with_context`) are correlated with the request, and the finish line's `duration_ms`
    and `response_size` cover the whole response."""

    def __init__(self, app: Flask, wsgi_app: WSGIApplication) -> None:
        self.app = app
        self.wsgi_app = wsgi_app

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
        exit_stack = ExitStack()
        exit_stack.enter_context(
            correlation.request_context(
                environ,
                alb_trace_id=correlation.parse_alb_trace_id(environ.get("HTTP_X_AMZN_TRACE_ID")),
                cloudfront_request_id=correlation.parse_cloudfront_request_id(environ.get("HTTP_X_AMZ_CF_ID")),
                debug_logging=False,
            )
        )
        response = _LoggedResponse(environ, exit_stack)

        try:
            iterable = self.wsgi_app(environ, response.wrap_start_response(start_response))
        except BaseException:
            response.status = response.status or 500
            response.close()
            raise

        response.wrap_iterable(iterable)
        return response


class _LoggedResponse:
    """The response iterable returned to the WSGI server: forwards the wrapped iterable's chunks, counting their bytes,
    and on `close()` logs the "Request finished" line and exits the request's unit of work. A streamed response also
    gets a DEBUG "Response streaming" line, logged at most once, when its headers are sent."""

    def __init__(self, environ: WSGIEnvironment, exit_stack: ExitStack) -> None:
        self._environ = environ
        self._exit_stack = exit_stack
        self._started_at = time.perf_counter()
        self._iterable: Iterable[bytes] = ()
        self._iterator: Iterator[bytes] = iter(())
        self._closed = False
        self.status: int | None = None
        self.response_streamed = False
        self.response_size = 0
        self.iteration_failed = False
        self._streaming_logged = False

    @property
    def _is_logged(self) -> bool:
        return not is_unlogged_path(self._environ.get("PATH_INFO", ""))

    def _method_and_path(self) -> tuple[str | None, str | None]:
        context = correlation.get_current_context()
        path = (context.path if context else None) or self._environ.get("PATH_INFO")
        return self._environ.get("REQUEST_METHOD"), path

    def wrap_start_response(self, start_response: StartResponse) -> StartResponse:
        def _start_response(status_line: str, headers: Any, exc_info: Any = None) -> Any:
            self.status = int(status_line.split(" ", 1)[0])
            self.response_streamed = not any(name.lower() == "content-length" for name, _ in headers)
            if self.response_streamed and not self._streaming_logged and self._is_logged:
                self._streaming_logged = True
                self._log_streaming()
            return start_response(status_line, headers, exc_info)

        return _start_response

    def wrap_iterable(self, iterable: Iterable[bytes]) -> None:
        self._iterable = iterable
        self._iterator = iter(iterable)

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        try:
            chunk = next(self._iterator)
        except StopIteration:
            raise
        except BaseException:
            self.iteration_failed = True
            raise
        self.response_size += len(chunk)
        return chunk

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        # The wrapped iterable is closed first so that anything it logs on close (eg request teardown for a
        # `stream_with_context` response) comes before the finish line.
        try:
            close_wrapped = getattr(self._iterable, "close", None)
            if close_wrapped is not None:
                close_wrapped()
        finally:
            try:
                if self._is_logged:
                    self._log_finished()
            finally:
                self._exit_stack.close()

    def _log_streaming(self) -> None:
        method, path = self._method_and_path()
        request_logger.debug(
            "Response streaming %(method)s %(path)s %(status)s",
            {"method": method, "path": path, "status": self.status},
            extra={"status": self.status},
        )

    def _log_finished(self) -> None:
        status = 500 if self.status is None and self.iteration_failed else self.status
        method, path = self._method_and_path()
        duration_ms = round((time.perf_counter() - self._started_at) * 1000, 2)
        log_args = {
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": duration_ms,
        }
        extra: dict[str, Any] = {
            "status": status,
            "duration_ms": duration_ms,
            "request_size": parse_request_size(self._environ.get("CONTENT_LENGTH")),
            "response_size": self.response_size,
            "response_streamed": self.response_streamed,
        }
        if user_agent := self._environ.get("HTTP_USER_AGENT"):
            extra["user_agent"] = user_agent[:_MAX_USER_AGENT_LENGTH]
        if client_ip := _client_ip(self._environ):
            extra["client_ip"] = client_ip

        request_logger.log(
            logging.WARNING if status is not None and status >= 500 else logging.INFO,
            "Request finished %(method)s %(path)s %(status)s in %(duration_ms)sms",
            log_args,
            extra=extra,
        )


def _client_ip(environ: WSGIEnvironment) -> str | None:
    # ProxyFix (in wsgi.py, wrapping the whole app) has already set `REMOTE_ADDR` from `X-Forwarded-For` using the
    # per-environment `PROXY_FIX_FOR` hop count. A value that is not an address can only come from a misconfigured hop
    # count, and is not logged.
    remote_addr = environ.get("REMOTE_ADDR")
    if not remote_addr:
        return None
    try:
        ipaddress.ip_address(remote_addr)
    except ValueError:
        return None
    return remote_addr


def parse_request_size(content_length: str | None) -> int:
    try:
        return int(content_length or 0)
    except ValueError:
        return 0


def attach_request_loggers(app: Flask) -> None:
    @app.before_request
    def bind_request_and_log_start() -> None:
        correlation.bind(
            method=request.method,
            path=request.path,
            endpoint=request.endpoint,
            user_id=_current_user_id(),
        )
        if not is_unlogged_path(request.path):
            request_logger.debug(
                "Request started %(method)s %(path)s", {"method": request.method, "path": request.path}
            )


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
    "is_unlogged_path",
    "parse_request_size",
    "route_loggers_through_app",
]
