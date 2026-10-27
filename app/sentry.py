import os
from collections.abc import Iterable
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
from sentry_sdk.types import Event, Hint

from app.common.data.types import TraceLevelEnum
from app.common.helpers.request_tracing import get_tracing_levels_from_environ
from app.config import Environment

_secret_key: str | None = None

INCOMING_TRACE_HEADER_ENVIRON_KEYS = ("HTTP_SENTRY_TRACE", "HTTP_BAGGAGE", "HTTP_TRACEPARENT", "HTTP_TRACESTATE")


class IgnoreIncomingTraceHeaders:
    """WSGI middleware that drops incoming distributed-tracing headers so every request starts a new trace.

    Clients (browsers) are outside our trust boundary and we do not run the Sentry browser SDK, so these headers have no
    legitimate source; honouring them would let a client choose the `trace_id` that our logs and Sentry events carry."""

    def __init__(self, wsgi_app: Any) -> None:
        self.wsgi_app = wsgi_app

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        for key in INCOMING_TRACE_HEADER_ENVIRON_KEYS:
            environ.pop(key, None)
        return self.wsgi_app(environ, start_response)


def errors_sampler(event: Event, sampling_context: Hint) -> float:
    return float(os.getenv("SENTRY_ERRORS_SAMPLE_RATE", "1"))


def _tracing_levels_from_context(sampling_context: Hint) -> list[TraceLevelEnum]:
    if not _secret_key:
        raise ValueError("Flask application secret key not configured for sentry")

    wsgi_environ = sampling_context.get("wsgi_environ")
    if not wsgi_environ:
        return []

    return get_tracing_levels_from_environ(wsgi_environ, _secret_key)


def traces_sampler(sampling_context: Hint) -> float:
    wsgi_environ = sampling_context.get("wsgi_environ")
    if wsgi_environ and wsgi_environ.get("PATH_INFO") == "/healthcheck":
        return 0

    if TraceLevelEnum.TRACE in _tracing_levels_from_context(sampling_context):
        return 1.0

    return float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.02"))


def profiles_sampler(sampling_context: Hint) -> float:
    wsgi_environ = sampling_context.get("wsgi_environ")
    if wsgi_environ and wsgi_environ.get("PATH_INFO") == "/healthcheck":
        return 0

    if TraceLevelEnum.PROFILE in _tracing_levels_from_context(sampling_context):
        return 1.0

    return float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.02"))


def init_sentry(secret_key: str) -> None:
    global _secret_key

    _secret_key = secret_key

    if os.getenv("SENTRY_DSN"):
        # Assume `production` here so that we 'fail closed', ie don't send PII/etc if this is unset or set incorrectly.
        env = Environment(os.getenv("FLASK_ENV", Environment.PROD.value))

        sentry_sdk.init(
            environment=env.value,
            send_default_pii=env is not Environment.PROD,
            error_sampler=errors_sampler,
            traces_sampler=traces_sampler,
            profiles_sampler=profiles_sampler,
            release=os.getenv("GITHUB_SHA"),
            _experiments={
                "enable_logs": True,
            },
            integrations=[
                # Sentry automatically configures most integrations, eg Flask, so we only list overrides here
                # https://docs.sentry.io/platforms/python/integrations/#available-integrations
                LoggingIntegration(sentry_logs_level=None),
            ],
        )

        # We disable the werkzeug logger in app/logging.py because we inject our own request+response log lines. This
        # should stay in sync with the logging config we use for the app. This may need to change when we add a proper
        # WSGI server (eg gunicorn) in front of Flask.
        ignore_logger("werkzeug")
