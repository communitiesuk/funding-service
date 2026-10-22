```
Title: Funding service user session management
Owner: Samuel Williams
Collaborator(s): n/a
Created on: 08/04/2025
Status: Accepted
Finalised on: 14/04/2025
```

## Overview

We need to decide how we want to manage user sessions on the "Funding as a Service" platform. On the existing pre-award/post-award apps, we use JWTs signed via the authenticator "service". JWTs are stored as cookies on the user's browser and are securely signed and stateless, meaning they are quick to validate and the claims embedded in them provide our services with all of the information needed to validate whether an action should be permitted or not.

## What is the current state?

The new "Funding as a Service" platform does not currently manage user sessions intentionally (because we don't have any login flow yet). We're adding a login flow now and need to make this decision.

The existing pre-award and post-award processes currently use the "authenticator" sub-service/module in pre-award. This creates JWTs as cookies for the user, and the signatures on those JWT cookies are trusted across both pre-award and post-award services. The JWTs are issued for local authority/third party users (who sign in via magic link) as well as MHCLG users (who sign in via MHCLG SSO). The JWTs contain a list of roles that are sourced from Entra ID; these are microsoft groups and they effectively determine coarse role-based access controls, such as "user can assess grant x", or "user can submit monitoring reports for grant x".

## Why should we change?

We think that the existing authentication flow for pre-award/post-award has some complexity and pitfalls that we may not want to reproduce, so are exploring options from scratch again.

We also just generally want a record of having gone through some intentional decision-making process for this (ie this RFC).

## General considerations

### Security
We need to manage session securely. If sessions can be tampered with, users could elevate their access to the platform and perform actions they aren't authorised to do.

All session cookies should be signed, and those signatures verified, so that users cannot push their own session cookies on us.

### Revocability
If we have an incident (eg sessions are leaked, secret keys are leaked) we may need to revoke all active sessions to protect our users.

### Cookie limits
A single cookie is limited to ~4kb, so we cannot store an excessive amount of information in it (although 4kb is quite a lot!).

## What are the main options?

### 1. Flask's basic session management
Flask sessions are by default stored in cookies on the user's browser, base64 encoded and signed to prevent tampering. All of the information in the cookie is essentially public to that user (if they know to decode it).

Revoking sessions would be tricky/coarse. We would need to rotate the SECRET_KEY, and this would invalidate _all_ sessions (plus anything else that Flask uses the SECRET_KEY for - which we'd need to carefully understand).

We would need to slightly think about how much data we store in the session, but even with the 4kb limit it feels like only a small consideration.

### 2. Server-side sessions stored in postgres
Store a session ID in a cookie, and have this link up to a `session` table in our postgres DB that stores the related session information (expiry, data, etc). This could be managed by something like [Flask-Session with a SQLAlchemy backend](https://flask-session.readthedocs.io/en/latest/api.html#flask_session.sqlalchemy.SqlAlchemySessionInterface) or [Flask-Sqlalchemy-Session](https://flask-sqlalchemy-session.readthedocs.io/en/v1.1/).

This would:
* avoid the end user having any visibility into the data stored in their session
* keep their session cookie small so requests stay fast (trivial consideration at our scale)
* give us an easy way to revoke active sessions if needed (truncate the table)

We might want to consider whether we'd need to truncate rows in the DB over time, for example removing expired sessions. Postgres doesn't natively provide anything to support this. If we reuse session rows for users, we could probably ignore this issue for a long time/forever - the number of users we anticipate (100s-1000s) will likely mean this is never a problem.

One negative consideration is that if all of the session data is stored in the DB, then malicious insiders/developers might be able to tamper with sessions if they have access to the production DB. This can be mitigated by strict access controls on developers getting into the DB, which we should intend to have in place regardless. We could also restrict permissions to read/write the session table specifically.

### 3. Server-side sessions stored in redis
As above, but using redis to store the session information.

The bonus here is that we could set expiries on the sessions and redis will automatically clean them up when they expire, so we don't need to have anything cleaning them up.

We don't currently have redis in our Funding as a Service infrastructure, so we would need to add it.

### 4. JWTs in cookies
This would be keeping a similar approach to the current pre-award/post-award authentication process. The platform would write JWTs to a cookie and store relevant claims in that token, which the server could trust (through signature verification) without needing to talk to the DB.

## Which option is preferred and why?

Option 4 with JWTs feel over-engineered for our architecture. These are often issued by a trusted service and then used with separate services; as we have a monolith, one of the key benefits of JWTs does not materialise for us.

Option 3 with server-side session in redis requires new infrastructure. We are intentionally trying to limit the number of things we have to 1) understand, 2) look after. Aside from session auto expiring, it feels strictly worse than option 2 (server-side sessions in postgres) - and the auto expiry is not enough of a benefit to justify choosing it.

Option 1 and 2 both feel like fairly acceptable options. We would prefer to go ahead with option 2, not out of an overwhelming amount of evidence guiding us that way, but for the following baseline reasons:
- we are choosing to rely on postgres for more things
- it removes (most) concerns about limits of session size
  - but we still shouldn't be putting huge amounts of arbitrary data in sessions
- reduced risk of us sending 'sensitive' data down to users

We will need to include some scheduled job/task that will clean up old sessions from the DB, because Flask-Session (for example) will append new rows each time rather than reuse rows per user. So by default that table will just grow infinitely. We should truncate expired sessions on [insert regular cadence].

**However**, Flask-Session - the library we'd use for this - does not currently support Flask-SQLAlchemy-Lite, the library we use for managing our database. We will try to get support added, but until/unless this happens, we will proceed with option 1 - storing session data in client-side signed cookies.

## Who will be affected?

This change should not materially impact (or even be noticed by) end users of the service. The main people interacting with this decision will be Funding Service developers.

Session management needs to be done securely and carefully; improper implementation could affect end users through eg incidents and abuse of the platform. We should use well known, trusted libraries/patterns/algorithms for session management.

## Who will benefit?

Funding Service developers should benefit if we choose an appropriate, simple, understandable session management mechanism.

## What are the key risks to manage or mitigate?

Session management will power a lot of our authorization processes (ie what a user can do). Getting it wrong could lead to users (maliciously or incidentally) being able to take actions on the platform that they shouldn't be able to. Decisions here should be carefully considered and the implementation should be scrutinised appropriately.
