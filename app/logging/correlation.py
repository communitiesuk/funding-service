"""
Correlation context for every HTTP request this codebase handles.

Every request enters exactly one `CorrelationContext`. It lives in a `ContextVar`, so it is isolated per greenlet
(gunicorn/gevent) and per thread (`flask run`). Every log record reads it at creation time (see
`CorrelatingLogRecordFactory`) and every Sentry event/transaction/log reads it from the Sentry isolation scope
tags/attributes that we set when the request starts.

Every request starts a new Sentry trace, whose `trace_id` is on every log line alongside the `request_id` and `user_id`.
Incoming trace headers (`sentry-trace`, `baggage`, `traceparent`, `tracestate`) are ignored, so a client cannot choose
the `trace_id` (see `app.sentry.IgnoreIncomingTraceHeaders` for the deployed path).
"""

import datetime
import enum
import logging
import re
import uuid
from collections.abc import Generator, Iterable, Mapping
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from dataclasses import fields as dataclass_fields
from enum import StrEnum
from typing import Any

import sentry_sdk

CORRELATION_RECORD_ATTR = "_correlation"

_ALB_TRACE_ROOT_RE = re.compile(r"1-[0-9a-f]{8}-[0-9a-f]{24}")
_CLOUDFRONT_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_=-]{1,128}")

# The value types that may be logged (see `app.logging.RejectMutableDataStructuresFilter`).
SCALAR_LOG_VALUE_TYPES = (str, int, float, bool, uuid.UUID, datetime.date, datetime.datetime, enum.Enum, type(None))

type LogFieldValue = str | int | float | bool

# Fields that are mirrored onto the Sentry isolation scope as tags (errors, transactions) and attributes (Sentry Logs,
# metrics). Request-shape fields (method/path/endpoint) are already recorded natively by Sentry's Flask integration.
_SENTRY_FIELDS = (
    "context_type",
    "request_id",
    "user_id",
    "alb_trace_id",
    "cloudfront_request_id",
)


class ContextType(StrEnum):
    REQUEST = "request"
    # Carried by gunicorn's own log lines (see `gunicorn.conf.py`, which cannot import this module); the application
    # never enters a unit of work of this type.
    SERVER = "server"


@dataclass(frozen=True, kw_only=True)
class CorrelationContext:
    context_type: ContextType
    request_id: str | None = None
    user_id: str | None = None
    method: str | None = None
    path: str | None = None
    endpoint: str | None = None
    alb_trace_id: str | None = None
    cloudfront_request_id: str | None = None
    debug_logging: bool = False

    def log_fields(self) -> dict[str, LogFieldValue]:
        log_fields: dict[str, LogFieldValue] = {
            key: str(value) for key, value in self._core_values().items() if value is not None
        }
        if self.debug_logging:
            log_fields["debug_logging"] = True
        return log_fields

    def _core_values(self) -> dict[str, Any]:
        return {
            context_field.name: getattr(self, context_field.name)
            for context_field in dataclass_fields(self)
            if context_field.name not in {"debug_logging"}
        }


# The `CorrelationContext` fields that `bind` may update; every other one identifies the unit of work and is fixed.
_BINDABLE_CONTEXT_FIELDS = frozenset({"user_id", "method", "path", "endpoint"})


_current_context: ContextVar[CorrelationContext | None] = ContextVar("correlation_context", default=None)


def get_current_context() -> CorrelationContext | None:
    return _current_context.get()


def new_id() -> str:
    return str(uuid.uuid4())


def bind(**changes: Any) -> None:
    """Update fields on the current unit of work, eg `user_id` after login/logout. Binding `None` removes a field.

    The change lasts until the unit of work exits. No-op outside a unit of work."""
    if unknown := changes.keys() - _BINDABLE_CONTEXT_FIELDS:
        raise ValueError(f"Cannot bind log fields {sorted(unknown)}.")
    context = _current_context.get()
    if context is None:
        return

    updated = replace(context, **changes)
    _current_context.set(updated)
    _apply_to_sentry_scope(updated)


def get_log_fields() -> dict[str, LogFieldValue]:
    """The correlation fields of the current unit of work, or `{}` outside one.

    Sentry's `trace_id` is stable for the whole unit of work and is the field to join on in Sentry. `span_id` is the
    active span's id while one is open, and otherwise the scope's propagation span id. For a request the active span is
    the HTTP transaction, which Sentry's WSGI middleware finishes before the response body is iterated and closed, so
    the "Request finished" line and lines logged while streaming a body can carry a different `span_id` from the lines
    logged during the handler."""
    context = _current_context.get()
    if context is None:
        return {}

    fields = context.log_fields()
    traceparent = sentry_sdk.get_traceparent()
    if traceparent:
        trace_id, _, rest = traceparent.partition("-")
        fields["trace_id"] = trace_id
        if span_id := rest.partition("-")[0]:
            fields["span_id"] = span_id
    return fields


def get_record_correlation(record: logging.LogRecord) -> Mapping[str, LogFieldValue]:
    return getattr(record, CORRELATION_RECORD_ATTR, {})


class CorrelatingLogRecordFactory:
    """Snapshots the correlation fields onto every log record at creation time.

    A record factory (rather than a logger or handler filter) enriches records from every logger and for every handler,
    including pytest's `caplog` handler. The fields are stored under a single private attribute so they can never
    collide with `extra=` keys and are skipped by Sentry's logging integration, which gets them from scope attributes
    instead."""

    def __init__(self, wrapped: Any) -> None:
        self.wrapped = wrapped

    def __call__(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
        record = self.wrapped(*args, **kwargs)
        setattr(record, CORRELATION_RECORD_ATTR, get_log_fields())
        return record


def install_log_record_factory() -> None:
    current_factory = logging.getLogRecordFactory()
    if isinstance(current_factory, CorrelatingLogRecordFactory):
        return
    logging.setLogRecordFactory(CorrelatingLogRecordFactory(current_factory))


def parse_alb_trace_id(header: str | None) -> str | None:
    """Extract the `Root=` segment of an `X-Amzn-Trace-Id` header, if it is exactly in the format the ALB generates."""
    if not header:
        return None
    for segment in header.split(";"):
        key, _, value = segment.strip().partition("=")
        if key == "Root" and _ALB_TRACE_ROOT_RE.fullmatch(value):
            return value
    return None


def parse_cloudfront_request_id(header: str | None) -> str | None:
    if header and _CLOUDFRONT_REQUEST_ID_RE.fullmatch(header):
        return header
    return None


def as_uuid_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _apply_to_sentry_scope(context: CorrelationContext) -> None:
    scope = sentry_sdk.get_isolation_scope()
    for key in _SENTRY_FIELDS:
        value = getattr(context, key)
        if value is None:
            _remove_from_sentry_scope((key,))
        else:
            scope.set_tag(key, str(value))
            scope.set_attribute(key, str(value))
            if key == "user_id":
                # The Sentry user is only ever the user's id: like our logs, Sentry attributes events to the user UUID,
                # never to a name or email address.
                scope.set_user({"id": str(value)})


def _remove_from_sentry_scope(keys: Iterable[str]) -> None:
    scope = sentry_sdk.get_isolation_scope()
    for key in keys:
        scope.remove_tag(key)
        scope.remove_attribute(key)
        if key == "user_id":
            scope.set_user(None)


def _restore_sentry_scope(previous: CorrelationContext | None) -> None:
    """Undo a unit of work's decoration of an isolation scope it did not fork, leaving the enclosing unit of work's
    view (if any) on it, so the shared scope is clean whoever owns it."""
    if previous is not None:
        _apply_to_sentry_scope(previous)
    else:
        _remove_from_sentry_scope(_SENTRY_FIELDS)


@contextmanager
def _enter(context: CorrelationContext, *, fork_sentry_scope: bool) -> Generator[CorrelationContext]:
    with ExitStack() as stack:
        if fork_sentry_scope:
            stack.enter_context(sentry_sdk.isolation_scope())
            sentry_sdk.continue_trace({})

        previous = _current_context.get()
        token = _current_context.set(context)
        stack.callback(_reset_current_context, token)
        if not fork_sentry_scope:
            # Registered after the reset, so it runs before it: ExitStack runs callbacks last in, first out.
            stack.callback(_restore_sentry_scope, previous)
        _apply_to_sentry_scope(context)
        yield context


def _reset_current_context(token: Token[CorrelationContext | None]) -> None:
    _current_context.reset(token)


@contextmanager
def request_context(
    environ: Mapping[str, Any], *, alb_trace_id: str | None, cloudfront_request_id: str | None, debug_logging: bool
) -> Generator[CorrelationContext]:
    """Entered by `app.logging.CorrelationMiddleware` for every HTTP request.

    When Sentry is active its WSGI middleware has already forked an isolation scope and started a new trace for this
    request, so we only decorate that scope, and undo the decoration on exit. When it is not (local dev, tests), we
    do the same thing ourselves so that every request still gets its own `trace_id`. Either way a request always starts
    a new trace: incoming trace headers are ignored (see `app.sentry.IgnoreIncomingTraceHeaders` for the deployed
    path)."""
    context = CorrelationContext(
        context_type=ContextType.REQUEST,
        request_id=new_id(),
        method=environ.get("REQUEST_METHOD"),
        path=environ.get("PATH_INFO"),
        alb_trace_id=alb_trace_id,
        cloudfront_request_id=cloudfront_request_id,
        debug_logging=debug_logging,
    )
    fork_sentry_scope = not sentry_sdk.get_client().is_active()
    with _enter(context, fork_sentry_scope=fork_sentry_scope):
        yield context
