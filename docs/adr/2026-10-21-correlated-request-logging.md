# ADR-2026-10-21: Correlated application logs

## Status

Accepted

Date of decision: 2026-10-20.

## Context and Problem Statement

The Funding Service platform is a single Flask application using gunicorn (gevent workers) on ECS, behind CloudFront
(with AWS WAF) and a private ALB. Logs are sent on stdout which ECS ships to CloudWatch Logs. Errors, traces, metrics
and logs are also sent to Sentry. Background workers are expected to come soon, probably using pgqueuer and running in
a separate ECS service.

Before this work, timestamps and log position were the only way to identify which logs were associated with a specific
request or action (outside of Sentry, where logs pick up Sentry's trace+span IDs). It should be easy to identify a
single request and see how it flowed through our system and what happened during that request, as well as who is
associated with that request.

Most, but not all, of our logs were structured JSON but there was a lack of consistency between various log streams
which made joining them more difficult. Commands like database migrations did not use structured JSON logging, and
gunicorn's access log duplicated what the application logged about each request.

### Questions this ADR answers

* How should we improve our logging to aid investigation and debugging?
* What approach should we use to provide consistency between requests, background jobs, CLI commands, etc?
* How much consistency do we want between local development and deployed web processes?
* How can we share context between processes, for example when a request triggers background jobs?

## Considered Options

* Do nothing
* Evolve the existing stdlib `logging` setup in place
* Replace stdlib logging with structlog and add an explicit bind API
* A 'unit of work' correlation context
* Use OpenTelemetry for context propagation and instrumentation

## Decision Outcome

A 'unit of work' correlation context, implemented as an extension of the stdlib `logging` module in the `app/logging`
package. This treats requests, CLI commands and (later) background jobs uniformly, adds no dependencies, and
keeps every Sentry-specific piece in one place so a later move to OpenTelemetry isn't a complete re-work.

### Units of work

An HTTP request and a CLI command each enter exactly one `CorrelationContext`, held in a `ContextVar` so it is isolated
per greenlet and per thread. A log record factory snapshots the context's fields onto every record at creation time,
from every logger and for every handler, so existing log calls needed no changes. The same fields are set as tags and
attributes on the Sentry isolation scope when the unit of work starts, so every Sentry error, transaction, log and
metric carries them too.

Every unit of work starts a new Sentry trace. Incoming `sentry-trace`, `baggage`, `traceparent` and `tracestate`
headers are stripped by a WSGI middleware that sits outside Sentry's own, so a client can never choose the `trace_id`
our logs and Sentry events have. The post-deploy smoke tests prove this through CloudFront and the ALB using
`/healthcheck/client`, which reports the request's own `trace_id`.

### Correlation fields

Every line inside a unit of work carries, when set:

| Field | Set for | Source |
| --- | --- | --- |
| `context_type` | Both | `request` or `cli`; gunicorn's own lines carry `server` |
| `trace_id`, `span_id` | Both | From the Sentry SDK's propagation context; `trace_id` is stable for the unit of work |
| `cli_command` | CLI | The full click command path, excluding arguments |
| `user_id` | Requests | Flask-Login's id from the signed session, no database hit; bound on login, removed on logout |
| `method`, `path`, `endpoint` | Requests | The request as routed |
| `alb_trace_id` | Requests | The `Root=` segment of `X-Amzn-Trace-Id`, only if it matches the ALB's format |
| `cloudfront_request_id` | Requests | `X-Amz-Cf-Id`, only if well formed |
| `debug_logging` | Requests | `true` when the unit of work opted in to debug logging (below) |

A field with no value is left off the line rather than logged as null. That includes an `alb_trace_id` or
`cloudfront_request_id` header that is missing or not in the expected format: the value is discarded, and the log line
is still written with the same structure and every other field.

Values are scalars only. A policy filter rejects log arguments that are lists or dicts, so personal data cannot be
logged by accident through a complex object. Correlation fields are written last by the JSON formatter, so they win
over any `extra=` key of the same name from our own or third-party code.

### Lifecycle lines

The application owns the request lifecycle lines, logged from the WSGI middleware so they are emitted even when an
exception propagates out of Flask and so streamed bodies are covered end to end:

| Level | Line | When |
| --- | --- | --- |
| DEBUG | `Request started METHOD PATH` | The request has been routed |
| DEBUG | `Response streaming` | A response without `Content-Length` sends its headers |
| WARNING | `Response body failed` | The application's body generator raises after the headers were sent |
| INFO | `Request finished METHOD PATH STATUS in Xms` | The response is complete |
| WARNING | `Request finished METHOD PATH STATUS in Xms` | The response is complete with a 5xx status or a failed body |

The `Request finished` line also carries `status`, `duration_ms`, `request_size`, `response_size`, `response_streamed`
and `iteration_failed`.

CLI commands get the same shape:

| Level | Line | When |
| --- | --- | --- |
| INFO | `Command finished <command> in Xms` | The command exits normally |
| WARNING | `Command finished <command> with exit code N in Xms` | The command exits with a non-zero exit code |
| ERROR | `Command failed <command> in Xms`, with the traceback | The command raises |

### Debug logging for one unit of work

The platform-admin developer tools page sets a signed, 15-minute `request_tracing` cookie whose levels can force Sentry
tracing, Sentry profiling and debug logging for that browser's requests. The application logger lets DEBUG records
through and a `ContextualLevelFilter` on each handler applies the configured `LOG_LEVEL` unless the current unit of work
asked for debug logging.

### The 500 page

The 500 error page shows the request's `trace_id` so a user can give the service desk one reference that finds the
request's log lines and Sentry events.

### Formats and other loggers

Deployed environments log one flat JSON object per line with snake_case keys, which CloudWatch Logs Insights discovers
automatically and which can be used in `filter`/`stats`. Local development logs a human-readable line ending in the
first 8 characters of the `trace_id` (`LOG_FORMATTER=plaintext`), or every correlation field (`plaintext-full`).

Third-party output is routed through the application's handlers so it shares the format and correlation fields:
alembic's runtime logger and its printed output (`flask db upgrade`, `heads`, `history`, ...), Python warnings via
`logging.captureWarnings` and the `py.warnings` logger, and the developer CLI commands, which log instead of echoing.
The werkzeug logger is disabled in favour of our own request lines.


### Deferred or not built

* **User agent and client IP** are not logged. The code is in place but disabled pending a privacy decision
  (FSPT-1805) about logging them and sending them to Sentry.
* **Background jobs** do not exist yet. The agreed shape, recorded in `app/logging/correlation.py`, is that a job is
  its own unit of work with its own `job_id`. The producer puts Sentry's trace headers, the `user_id` and the
  `debug_logging` flag into the job message; the consumer continues the trace and validates every inherited value,
  because the message is data, not trusted context.
* **Startup** is not a unit of work: lines logged while `create_app` runs carry no correlation fields.

### Migrating to OpenTelemetry later

The Sentry-specific pieces sit behind a few areas, so a move to OpenTelemetry would be a swap of what sits behind them
rather than a redesign. `trace_id` and `span_id` come from one call in `get_log_fields`, which would read the current
OpenTelemetry span context instead of `sentry_sdk.get_traceparent()`; the field names, the 500 page,
`/healthcheck/client` and any CloudWatch queries would not change. Careful consideration would have to be given to
OpenTelemetry's trace+span start+end points, making sure that all logs from request started to request finished
include the correct parent trace id; this may need some finagling to work with its WSGI instrumentation.

A few things would stay custom/customised by us:

- the inject-only propagator that keeps a client from choosing our trace id or setting our baggage
  (`OTEL_PROPAGATORS=none` is the off-the-shelf alternative if we never need to inject)
- the middleware that writes the request lifecycle lines and byte counts
- the code that names command spans after the full command path and drops the argument values

Also, some thought needs to be given to how OTel and Sentry fit together, and essentially then where we are directing
errors, logs, and traces. At the moment Sentry gets all three. If we use custom OTel, it might be the case that we
only use Sentry for errors, and ship logs+traces to something else for storage and visualisation/analysis.

## Pros and Cons of the Options

### Do nothing

Live with our current logging implementations and accept that observability and traceability will be a bit fuzzy and
require a lot of manual, time-consuming, detailed work.

Good because:
* it means we don't have to do any work now
* Sentry already correlates application logs for us

Bad because:
* Sentry doesn't expose our infrastructure logs (eg cloudfront, ALB, etc)
* when we want to investigate problems or errors it will take time and effort to narrow down the context
* we don't record user ID on logs
* we don't have a simple way to associate requests with upcoming background worker jobs

### Evolve the existing stdlib `logging` setup in place

Keep the current module and add the request and user IDs to it with the smallest possible change.

Good because:
* it is the smallest change and uses tools the team already knows
* it adds no dependencies

Bad because:
* it is shaped around web requests and has no natural place for background jobs or CLI commands
* it doesn't give us correlation fields for background jobs or CLI commands

### Replace stdlib logging with structlog and add an explicit bind API

Adopt structlog as the logging library, giving application code a dedicated API for attaching context to log lines.

Good because:
* it has the nicest API for attaching context, and a very readable local development output
* it is widely used and has native async loggers that future workers could use

Bad because:
* our existing log calls would stay on the stdlib unless we migrate them all, leaving two styles in use
* Sentry's logging integration works through the stdlib, so native structlog calls need extra wiring
* it adds a dependency and a new mental model for a modest gain over the stdlib

### A 'unit of work' correlation context

Treat a request, a background job and a CLI command as the same kind of thing: a unit of work that carries a set of
correlation fields. Every log line and Sentry event inside it picks those fields up automatically, and the fields can be
handed to another process, for example into a job's payload.

Good because:
* requests, jobs and commands are handled consistently, now and when workers arrive
* context crosses process boundaries using Sentry's trace propagation, which we already have
* it adds no dependencies and existing log calls keep working unchanged

Bad because:
* it is more code for us to own than evolving the current module
* trace and span IDs come from Sentry's SDK, so we are tied to how that SDK evolves

### Use OpenTelemetry for context propagation and instrumentation

Adopt the OpenTelemetry SDK and its Flask, database and logging instrumentation, bridged into Sentry.

Good because:
* it is a vendor-neutral standard that would survive a move away from Sentry
* propagation between processes and automatic instrumentation already exist

Bad because:
* Sentry is our only consumer today, so everything would be translated into Sentry anyway
* it does not give us the user ID, the AWS IDs or the command name; we would still build that part
* it adds several dependencies, and OpenTelemetry's Python logging support is still maturing

This option is deferred rather than rejected: the chosen approach keeps all Sentry-specific propagation in one place, so
switching to OpenTelemetry later is a contained change (see "Migrating to OpenTelemetry later" above). A spike on the
`logging/otel-spike` bookmark rebuilt the design on the OpenTelemetry libraries and found that the lifecycle lines, the
inject-only propagator, the tracing cookie handling and the command naming would all still be ours to write, while
Sentry transactions, profiling and the `Command failed` tracebacks would be lost or changed.

## More Information

* The implementation lives in the `app/logging` package: `correlation.py` (the context, Sentry scope mirroring,
  header parsing), `__init__.py` (configuration, middleware, lifecycle lines, filters, formatters, CLI hooks),
  `unlogged.py` (paths that are never logged or sampled) and `cli_output.py` (alembic output routing).
* The description of https://github.com/communitiesuk/funding-service/pull/2177 has a diagram of how a request flows
  through AWS infrastructure. It predates the removal of `request_id` in favour of `trace_id`.
* Sentry distributed tracing headers: https://develop.sentry.dev/sdk/telemetry/traces/#header-sentry-trace
* W3C Trace Context: https://www.w3.org/TR/trace-context/
* CloudWatch Logs Insights field discovery:
  https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_AnalyzeLogData-discoverable-fields.html
