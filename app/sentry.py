import os

import sentry_sdk
from sentry_sdk.types import Event, Hint


def errors_sampler(event: Event, sampling_context: Hint) -> float:
    return float(os.getenv("SENTRY_ERRORS_SAMPLE_RATE", "1"))


def traces_sampler(sampling_context: Hint) -> float:
    wsgi_environ = sampling_context.get("wsgi_environ")
    if wsgi_environ and wsgi_environ.get("PATH_INFO") == "/healthcheck":
        return 0

    return float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.02"))


def profiles_sampler(sampling_context: Hint) -> float:
    wsgi_environ = sampling_context.get("wsgi_environ")
    if wsgi_environ and wsgi_environ.get("PATH_INFO") == "/healthcheck":
        return 0

    return float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.02"))


def init_sentry() -> None:
    if os.getenv("SENTRY_DSN"):
        # Assume `production` here so that we 'fail closed', ie don't send PII/etc if this is unset or set incorrectly.
        env = os.getenv("FLASK_ENV", "production")

        sentry_sdk.init(
            environment=env,
            send_default_pii=env.lower() in ["development", "dev", "test"],
            error_sampler=errors_sampler,
            traces_sampler=traces_sampler,
            profiles_sampler=profiles_sampler,
            release=os.getenv("GITHUB_SHA"),
        )
