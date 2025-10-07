from __future__ import absolute_import

import datetime
import logging
import time
from logging import LogRecord
from logging.config import dictConfig
from os import getpid
from threading import get_ident as get_thread_ident
from typing import Any, cast

from flask import Flask, Response, current_app, request
from flask.ctx import has_request_context
from pythonjsonlogger.core import LogData
from pythonjsonlogger.json import JsonFormatter as BaseJSONFormatter


def _common_request_extra_log_context() -> dict[str, Any]:
    return {
        "method": request.method,
        "url": request.url,
        "endpoint": request.endpoint,
        # pid and thread ident are both available on LogRecord by default,
        # as `process` and `thread` respectively, but I don't see a
        # straightforward way of selectively including them only in certain
        # log messages - they are designed to be included when the formatter
        # is being configured. This is why I'm manually grabbing them and
        # putting them in as `extra` here, avoiding the existing parameter
        # names to prevent LogRecord from complaining
        "process_": getpid(),
        # stringifying this as it could potentially be a long that json is
        # unable to represent accurately
        "thread_": str(get_thread_ident()),
    }


def get_default_logging_config(app: Flask) -> dict[str, Any]:
    log_level = app.config["LOG_LEVEL"]
    formatter = app.config["LOG_FORMATTER"]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_extra_context": {
                "()": "app.logging.RequestExtraContextFilter",
            },
            "reject_mutable_data_structures": {
                "()": "app.logging.RejectMutableDataStructuresFilter",
            },
        },
        "formatters": {
            "plaintext": {
                "()": "logging.Formatter",
                "fmt": "%(asctime)s %(levelname)s - %(message)s - from %(funcName)s() in %(filename)s:%(lineno)d",
            },
            "json": {
                "()": "app.logging.JSONFormatter",
                "fmt": "%(name)s %(levelname)s - %(message)s - from %(funcName)s in %(pathname)s:%(lineno)d",
            },
        },
        "handlers": {
            "null": {
                "class": "logging.NullHandler",
            },
            "sentry": {
                "class": "sentry_sdk.integrations.logging.SentryLogsHandler",
                # These filters do not actually affect what ends up in Sentry - request_extra_context is not actually
                # used in this codebase as of 22/04/25, and even if it _was_ used, the SentryLogsHandler would not
                # include that extra info in the log shipped to sentry. We'd need to inject a `before_send_logs`
                # handler in sentry directly (this is currently experimental). Leaving for the future, if we need it.
                # "filters": ["request_extra_context", "reject_mutable_data_structures"],
                #
                # ---
                #
                # Likewise, the formatter doesn't affect what gets sent to Sentry as of 22/04/25 - it reads the message
                # template directly rather than the interpolated string. So passing this through a JSON formatter
                # does not actually mean we send JSON logs to Sentry.
                # "formatter": formatter,
            },
            "default": {
                "filters": ["request_extra_context", "reject_mutable_data_structures"],
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
    log_config = log_config or get_default_logging_config(app)
    dictConfig(log_config)
    attach_request_loggers(app)


def attach_request_loggers(app: Flask) -> None:
    @app.before_request
    def before_request() -> None:
        # annotating these onto request instead of flask.g as they probably
        # shouldn't be inheritable from a request-less application context
        request.before_request_real_time = time.perf_counter()  # type: ignore[attr-defined]
        request.before_request_process_time = time.process_time()  # type: ignore[attr-defined]

        if request.path != "/healthcheck":
            current_app.logger.info(
                "--- %(method)s %(url)s",
                _common_request_extra_log_context(),
                extra=_common_request_extra_log_context(),
            )

    @app.after_request
    def after_request(response: Response) -> Response:
        if request.path != "/healthcheck":
            log_data = {
                "status": response.status_code,
                "duration_real": (
                    (time.perf_counter() - cast(float, request.before_request_real_time))
                    if hasattr(request, "before_request_real_time")
                    else None
                ),
                "duration_process": (
                    (time.process_time() - cast(float, request.before_request_process_time))
                    if hasattr(request, "before_request_process_time")
                    else None
                ),
                **_common_request_extra_log_context(),
            }
            current_app.logger.info(
                "%(status)s %(method)s %(url)s - [real:%(duration_real).2fs] [process:%(duration_process).2fs]",
                log_data,
                extra=log_data,
            )
        return response


class RequestExtraContextFilter(logging.Filter):
    """
    Filter which will pull extra context from
    the current request's `get_extra_log_context` method
    (if present) and make this available on log records
    """

    def filter(self, record: LogRecord) -> LogRecord:
        if has_request_context():
            get_extra_log_context = getattr(request, "get_extra_log_context", None)
            if callable(get_extra_log_context):
                for key, value in get_extra_log_context().items():
                    setattr(record, key, value)

        return record


class RejectMutableDataStructuresFilter(logging.Filter):
    def filter(self, record: LogRecord) -> LogRecord:
        logging_msg_args: dict[str, Any] | None
        if isinstance(record.args, tuple):
            logging_msg_args = record.args[0] if len(record.args) > 0 else None  # type: ignore[assignment]
        else:
            logging_msg_args = record.args  # type: ignore[assignment]

        if not logging_msg_args:
            return record

        for _k, v in logging_msg_args.items():
            if not isinstance(v, str | int | float | bool | None):
                # We want to only allow basic data types to be logged. There is a security/data protection risk that
                # comes with logging more complex types like lists and dicts; it is easier to accidentally include
                # PII, or to make a change in the future that adds it without realising we'll end up logging it out.
                raise ValueError(f"Attempt to log data type `{type(v)}` rejected by security policy.")
        return record


class JSONFormatter(BaseJSONFormatter):
    def formatTime(self, record: LogRecord, datefmt: str | None = None) -> str:
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            s = (
                datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
                .astimezone()
                .isoformat(sep=" ", timespec="milliseconds")
            )
        return s

    def process_log_record(self, log_record: LogData) -> LogData:
        for key, newkey in (
            ("asctime", "time"),
            ("trace_id", "requestId"),
        ):
            try:
                log_record[newkey] = log_record.pop(key)
            except KeyError:
                pass

        log_record["logType"] = "application"

        return log_record
