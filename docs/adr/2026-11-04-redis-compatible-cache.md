```
Title: Use Amazon ElastiCache for Valkey
Owner: Tudor Monkley
Collaborator(s): Platform team
Created on: 2026-11-04
Status: Draft
Finalised on:
```

## Overview

The Funding Service will use Amazon ElastiCache with the Valkey engine when it needs a cache or other short-lived shared
state. The application will connect using the Redis protocol and a `REDIS_URL` environment variable.

## What is the current state?

The application does not currently use a cache for user-facing functionality. It now has the small amount of support
needed to establish a connection and check it with Redis `PING`.

When `REDIS_URL` is set, the application creates a Redis client with short connection and socket timeouts. The existing
`/healthcheck` endpoint pings the store and returns `500 ERROR` if the check fails. When the variable is not set, the
application can still start and the health check remains healthy. This keeps local unit tests and development contexts
that do not need Redis usable.

## Why are we doing this?

We need a shared, low-latency key-value store. Amazon ElastiCache provides the managed AWS service and Valkey provides
the Redis-compatible engine. Using the Redis protocol keeps the application contract small and avoids an AWS-specific
client in this repository.

The health check makes a configured store failure visible to the existing ECS and load-balancer health checking. It
does not expose the connection URL or exception details in the response.

## Considered options

* Use Amazon ElastiCache for Valkey through `REDIS_URL`.
* Use Amazon ElastiCache for Redis OSS through `REDIS_URL`.
* Run Valkey ourselves rather than using a managed AWS service.
* Use LocalStack to provide ElastiCache locally.
* Do not add application-side support until a cache feature needs it.

## Decision outcome

Use Amazon ElastiCache for Valkey in AWS. The application will continue to use the Redis protocol through `REDIS_URL`,
so the managed service is hidden behind a simple configuration value. Local development will use a plain Redis
container because it provides the same protocol without needing LocalStack.

The application initially needs access only for the Funding Service ECS task. Ad-hoc tasks do not currently require
Redis, but they can use the same contract later if a task needs shared cache state.

## Pros and cons of the options

### Use Amazon ElastiCache for Valkey through `REDIS_URL`

Good because:

* The application contract is small and portable.
* Local development can use a normal Redis container without LocalStack.
* Valkey is Redis-compatible, so no AWS-specific client is needed.
* Connection failures are visible through the existing health endpoint.

Neutral because:

* The application does not yet provide cache read/write functionality; this decision only establishes connectivity.

Bad because:

* Infrastructure must provide the URL, network access, authentication, and TLS settings.

### Use Amazon ElastiCache for Redis OSS through `REDIS_URL`

Good because:

* It provides the same managed service and a familiar Redis engine.

Bad because:

* Valkey is the preferred engine for this decision and avoids tying the new store to Redis OSS.

### Run Valkey ourselves

Good because:

* We would have direct control over the deployment.

Bad because:

* We would take on patching, failover, backups, monitoring, and capacity management.
* It does not fit the existing AWS-managed infrastructure.

### Use LocalStack to provide ElastiCache locally

Good because:

* More of the AWS service boundary could be exercised locally.

Bad because:

* It adds complexity for a connectivity check that only needs the Redis protocol.
* LocalStack is not required for the application contract and would make local development heavier.

### Do not add application-side support yet

Good because:

* There would be no new dependency or health-check behaviour.

Bad because:

* Infrastructure could not provide the store through a documented application contract.
* Connectivity would not be verified by the application’s existing health check.

## What is outside this decision?

The infrastructure repository must create and configure ElastiCache for Valkey, the customer-managed KMS key,
encryption, authentication, private networking, security groups, ECS environment wiring, and CloudWatch alarms. Those
concerns are not configured in this application repository.

If cache functionality is introduced later, its key naming, expiry, read/write behaviour, failure policy, and metrics
will need a separate design decision. In particular, cache hit/miss alarms are only meaningful once the application
performs cache reads and writes.
