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
state. The application will connect using the Redis protocol and a `CACHE_URL` environment variable.

## What is the current state?

The application does not currently use a cache for user-facing functionality. This decision establishes the provider,
the Redis-compatible application contract, and the intention to use the store for user sessions. Cache key and value
structure will be defined alongside the first feature that uses the store.

## Why are we doing this?

We need a shared, low-latency key-value store. Amazon ElastiCache provides the managed AWS service and Valkey provides
the Redis-compatible engine. Using the Redis protocol keeps the application contract small and avoids an AWS-specific
client in this repository.

The `/healthcheck/db` endpoint makes a configured store failure visible to operators and deployment checks. It returns
HTTP 200 with the dependency status in the response, so it is diagnostic rather than a liveness check. It does not
expose the connection URL or exception details in the response.

## Considered options

* Use Amazon ElastiCache for Valkey through `CACHE_URL`.
* Use Amazon ElastiCache for Redis OSS through `CACHE_URL`.
* Run Valkey ourselves rather than using a managed AWS service.
* Do not add application-side support until a cache feature needs it.

The first two options are provider/engine variants of the same application contract; they are listed separately because
the engine choice is part of the infrastructure decision.

## Decision outcome

Use Amazon ElastiCache for Valkey in AWS. The application will continue to use the Redis protocol through `CACHE_URL`,
so the managed service is hidden behind a simple configuration value. Local development will use a Valkey container
because it provides the same protocol and version family without needing LocalStack.

The application initially needs access only for the Funding Service ECS task. Ad-hoc tasks do not currently require
Redis, but they can use the same contract later if a task needs shared cache state. The application will keep a clear
registry of cache keys and value structures when cache-backed features are introduced, rather than allowing ad-hoc
keys to accumulate across the codebase.

## Pros and cons of the options

### Use Amazon ElastiCache for Valkey through `CACHE_URL`

Good because:

* The application contract is small and portable.
* Local development can use a Valkey container without LocalStack.
* Valkey is Redis-compatible, so no AWS-specific client is needed.
* Connection failures are visible through the existing health endpoint.

Neutral because:

* The application does not yet provide cache read/write functionality; this decision only establishes connectivity.

Bad because:

* Infrastructure must provide the URL, network access, authentication, and TLS settings.

### Use Amazon ElastiCache for Redis OSS through `CACHE_URL`

Good because:

* It provides the same managed service and a familiar Redis engine.

Bad because:

* AWS now offers Valkey as the preferred open-source-compatible engine for this decision, so choosing Redis OSS would
  tie new work to the older engine choice without providing a different application contract.
* Redis-compatible does not mean identical: application code must stay within the command set supported by the Valkey
  version deployed in AWS.

### Run Valkey ourselves

Good because:

* We would have direct control over the deployment.

Bad because:

* We would take on patching, failover, backups, monitoring, and capacity management.
* It does not fit the existing AWS-managed infrastructure.

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

The deployed ElastiCache version is Valkey 7.2, using the `default.valkey7` parameter group. The local
Redis-compatible image is therefore Valkey 7.2 as well. It is declared once in `docker-compose.yml`; integration tests
read that value directly so they cannot drift from local development. Renovate is constrained to the 7.2 line and must
be updated together with the infrastructure version if AWS moves to a different Valkey version.
