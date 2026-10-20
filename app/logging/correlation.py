"""
Correlation context for every "unit of work" this codebase runs: an HTTP request, a CLI command, or the startup work
done in `create_app`.

Every unit of work enters exactly one `CorrelationContext`. It lives in a `ContextVar`, so it is isolated per greenlet
(gunicorn/gevent) and per thread (`flask run`). Every log record reads it at creation time (see
`CorrelatingLogRecordFactory`) and every Sentry event/transaction/log reads it from the Sentry isolation scope
tags/attributes that we set when the unit of work starts.

Every request and every CLI command starts a new Sentry trace, whose `trace_id` is on every log line alongside the
`request_id` (requests) or `run_id` (CLI commands and startup work) and the `user_id`. Incoming trace headers
(`sentry-trace`, `baggage`, `traceparent`, `tracestate`) are ignored, so a client cannot choose the `trace_id` (see
`app.sentry.IgnoreIncomingTraceHeaders` for the deployed path). A unit of work nested inside another in the same
process (eg `seed_system_data` startup work inside a CLI command) gets its own `run_id` and Sentry isolation scope but
continues the enclosing unit of work's Sentry trace, so it shares the `trace_id` and has its own `span_id` (see
https://docs.sentry.io/platforms/python/tracing/distributed-tracing/custom-instrumentation/ and
https://develop.sentry.dev/sdk/miscellaneous/hub_and_scope_refactoring/).

Background jobs (not yet implemented): a job should be its own unit of work with its own `job_id`, never inheriting the
`request_id` or `run_id` of the unit of work that enqueued it. The producer should put `sentry_sdk.get_traceparent()`
and `sentry_sdk.get_baggage()`, plus `user_id` and `debug_logging`, into the job message; the consumer should enter a
forked isolation scope, call `sentry_sdk.continue_trace(headers)` and start a `queue.process` transaction, validating
every inherited value (bounded strings, a UUID for `user_id`) because the message is data, not trusted context (see
https://docs.sentry.io/platforms/python/tracing/instrumentation/custom-instrumentation/queues-module/).

Application fields (not yet implemented): a unit of work could later carry application identifiers such as
`grant_id`, `organisation_id` and `collection_id`, so that every later line of the request and its Sentry events are
filterable by them. The shape would be `bind(grant_id=...)` to set a field until the unit of work exits, and a
`bound(...)` context manager to set fields for a block and restore the previous values on exit. Values must be scalars
(`SCALAR_LOG_VALUE_TYPES`) and must not reuse a correlation field name; the fields should be mirrored onto the Sentry
isolation scope as tags/attributes like the fixed fields are, and never inherited by nested or background units of
work. The natural place to bind them is where the object is loaded for the request (the grant-role decorators or the
data interfaces), which should be agreed before the mechanism is added.
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

import click
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
    "run_id",
    "cli_command",
    "startup_task",
    "user_id",
    "alb_trace_id",
    "cloudfront_request_id",
)


class ContextType(StrEnum):
    REQUEST = "request"
    CLI = "cli"
    STARTUP = "startup"
    # Carried by gunicorn's own log lines (see `gunicorn.conf.py`, which cannot import this module); the application
    # never enters a unit of work of this type.
    SERVER = "server"


@dataclass(frozen=True, kw_only=True)
class CorrelationContext:
    context_type: ContextType
    request_id: str | None = None
    # Identifies a CLI command or startup unit of work; requests have `request_id`.
    run_id: str | None = None
    cli_command: str | None = None
    startup_task: str | None = None
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
_BINDABLE_CONTEXT_FIELDS = frozenset({"user_id", "cli_command", "method", "path", "endpoint"})


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
    if context.context_type is ContextType.CLI:
        context = _refresh_cli_command(context)

    fields = context.log_fields()
    traceparent = sentry_sdk.get_traceparent()
    if traceparent:
        trace_id, _, rest = traceparent.partition("-")
        fields["trace_id"] = trace_id
        if span_id := rest.partition("-")[0]:
            fields["span_id"] = span_id
    return fields


def _refresh_cli_command(context: CorrelationContext) -> CorrelationContext:
    """Refine a CLI unit of work's `cli_command` to the deepest click command path seen so far (eg `flask` to
    `flask db upgrade`), returning the up-to-date context.

    This is done lazily, as records are created, because the unit of work starts while `create_app` runs, before click
    has resolved the subcommand, and Flask then keeps one app context active for the whole invocation: the subcommand
    pushes no further app context, so there is no later push to hook. The path is only ever refined deeper, never
    replaced by a shorter or different one: once the subcommand's click context exits the root context (`flask`) is
    current again, and lines logged then still belong to the subcommand."""
    click_ctx = click.get_current_context(silent=True)
    if click_ctx is None:
        return context
    command_path = click_ctx.command_path
    if context.cli_command is None or command_path.startswith(f"{context.cli_command} "):
        bind(cli_command=command_path)
        return _current_context.get() or context
    return context


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


def _current_trace_headers() -> dict[str, str]:
    """The Sentry trace of the current unit of work, for a nested unit of work in this process to continue. Empty
    outside a unit of work, so a top-level unit of work starts a new trace."""
    if _current_context.get() is None:
        return {}
    headers = {}
    if traceparent := sentry_sdk.get_traceparent():
        headers["sentry-trace"] = traceparent
    if baggage := sentry_sdk.get_baggage():
        headers["baggage"] = baggage
    return headers


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
def _enter(
    context: CorrelationContext, *, fork_sentry_scope: bool, sentry_headers: Mapping[str, str] | None = None
) -> Generator[CorrelationContext]:
    with ExitStack() as stack:
        if fork_sentry_scope:
            # Each unit of work is its own isolation boundary, like an incoming HTTP request; see
            # https://develop.sentry.dev/sdk/miscellaneous/hub_and_scope_refactoring/
            stack.enter_context(sentry_sdk.isolation_scope())
            sentry_sdk.continue_trace(dict(sentry_headers or {}))

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


@contextmanager
def cli_context(command: str | None) -> Generator[CorrelationContext]:
    context = CorrelationContext(
        context_type=ContextType.CLI,
        run_id=new_id(),
        cli_command=command,
    )
    with _enter(context, fork_sentry_scope=True, sentry_headers=_current_trace_headers()):
        yield context


@contextmanager
def startup_context(name: str) -> Generator[CorrelationContext]:
    context = CorrelationContext(
        context_type=ContextType.STARTUP,
        run_id=new_id(),
        startup_task=name,
    )
    with _enter(context, fork_sentry_scope=True, sentry_headers=_current_trace_headers()):
        yield context
