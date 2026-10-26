# ADR-2026-10-21: Correlated application logs

## Status

Draft

Date of decision:

## Context and Problem Statement

The Funding Service platform is a single Flask application using gunicorn (gevent workers) on ECS, behind CloudFront and
a private ALB. Logs are sent on stdout which ECS ships to CloudWatch Logs. Errors, traces, metrics and logs are also
sent to Sentry. Background workers are expected to come soon, probably using pgqueuer and running in a separate ECS
service.

Currently, timestamps and log position are the only way to identify which logs are associated with a specific request or
action (outside of Sentry, where logs pick up Sentry's trace+span IDs). It should be easy to identify a single request
and see how it flowed through our system and what happened during that request, as well as who is associated with that
request.

Most, but not all, of our logs are structured JSON but there is a lack of consistency between various log streams which
makes joining them more difficult. Commands like database migrations don't use structured JSON logging.

How should we improve our logging to aid investigation and debugging? What approach should we use to provide consistency
between requests, background jobs, CLI commands, etc? How much consistency do we want between local development and
deployed web processes? How can we share context between processes, for example when a request triggers background jobs?

## Considered Options

* Do nothing
* Evolve the existing stdlib `logging` setup in place
* Replace stdlib logging with structlog and add an explicit bind API
* A 'unit of work' correlation context
* Use OpenTelemetry for context propagation and instrumentation

## Decision Outcome

Implement a 'unit of work' correlation context as an extension on the stdlib `logging` module, creating a unique
identifier for every context (request, command, background job, etc). As appropriate, include all of the following bits
of standard context:

* [Request/CLI/job] ID
* User ID
* ALB trace ID
* CloudFront request ID
* Method / path / endpoint
* Sentry trace_id and span_id
* HTTP response status code / duration / request_size / response_size
* HTTP user agent and client IP
* CLI Command

In practice this means:

* The application logs the start and end of every request itself, with the context above, and gunicorn's access log is
  retired so each request is logged once.
* The same context is attached to everything sent to Sentry, so a CloudWatch log line and a Sentry event can be found
  from each other.
* Background jobs, CLI commands and startup tasks get the same treatment as requests. A job started by a request carries
  that request's ID and continues its Sentry trace.
* Deployed environments log JSON. Local development logs a short human-readable line by default, with the full context
  available on demand.
* Optionally: the request ID is shown on the 500 error page so users can quote it to the service desk.

We'll continue to use Sentry and/or CloudWatch Log Insights to search and review logs, rather than a new piece of
infrastructure like an ELK/Elastic Stack or Honeycomb.

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
* it keeps some legacy choices we would rather drop, such as logging full URLs including query strings

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

Treat a request, a background job, a CLI command and a startup task as the same kind of thing: a unit of work that
carries a set of correlation fields. Every log line and Sentry event inside it picks those fields up automatically, and
the fields can be handed to another process, for example into a job's payload.

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
* it does not give us our own request ID, user ID or the AWS IDs; we would still build that part
* it adds several dependencies, and OpenTelemetry's Python logging support is still maturing

This option is deferred rather than rejected: the chosen approach keeps all Sentry-specific propagation in one place,
so switching to OpenTelemetry later is a contained change.

## More Information

* The implementation will live in the `app/logging` package
* Sentry distributed tracing headers: https://develop.sentry.dev/sdk/telemetry/traces/#header-sentry-trace
* W3C Trace Context: https://www.w3.org/TR/trace-context/
* CloudWatch Logs Insights field discovery:
  https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_AnalyzeLogData-discoverable-fields.html
