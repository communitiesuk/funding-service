from __future__ import absolute_import

import datetime
import logging
import time
from logging import LogRecord
from logging.config import dictConfig
from os import getpid
from threading import get_ident as get_thread_ident
from typing import Any

from flask import Flask, current_app, request, Response
from flask.ctx import has_request_context

from pythonjsonlogger.json import JsonFormatter as BaseJSONFormatter
from pythonjsonlogger.core import LogRecord as JSON_LogRecord


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
                "()": "app.common.logging.RequestExtraContextFilter",
            },
        },
        "formatters": {
            "plaintext": {
                "()": "logging.Formatter",
                "fmt": "%(asctime)s %(levelname)s - %(message)s - from %(funcName)s() in %(filename)s:%(lineno)d",
            },
            "json": {
                "()": "app.common.logging.JSONFormatter",
                "fmt": "%(name)s %(levelname)s - %(message)s - from %(funcName)s in %(pathname)s:%(lineno)d",
            },
        },
        "handlers": {
            "null": {
                "class": "logging.NullHandler",
            },
            "default": {
                "filters": ["request_extra_context"],
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
                "disabled": False,
            },
            app.name: {
                "handlers": ["default"],
                "level": log_level,
            },
        },
    }


def init_app(app: Flask, log_config: dict[str, Any] | None = None) -> None:
    log_config = log_config or get_default_logging_config(app)
    dictConfig(log_config)
    attach_request_loggers(app)
    app.logger.info("Logging configured")


def attach_request_loggers(app: Flask) -> None:
    @app.before_request
    def before_request() -> None:
        # annotating these onto request instead of flask.g as they probably
        # shouldn't be inheritable from a request-less application context
        request.before_request_real_time = time.perf_counter()  # type: ignore[attr-defined]
        request.before_request_process_time = time.process_time()  # type: ignore[attr-defined]

        current_app.logger.log(
            logging.DEBUG,
            "Received request %(method)s %(url)s",
            _common_request_extra_log_context(),
            extra=_common_request_extra_log_context(),
        )

    @app.after_request
    def after_request(response: Response) -> Response:
        if request.path != "/healthcheck":
            log_data = {
                "status": response.status_code,
                "duration_real": (
                    (time.perf_counter() - request.before_request_real_time)
                    if hasattr(request, "before_request_real_time")
                    else None
                ),
                "duration_process": (
                    (time.process_time() - request.before_request_process_time)
                    if hasattr(request, "before_request_process_time")
                    else None
                ),
                **_common_request_extra_log_context(),
            }
            current_app.logger.log(
                logging.INFO, "%(method)s %(url)s %(status)s", log_data, extra=log_data
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

    def process_log_record(self, log_record: JSON_LogRecord) -> JSON_LogRecord:
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
