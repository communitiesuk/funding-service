"""
Requests that must not produce "Request started"/"Response streaming"/"Request finished" lines and must never be
sampled for Sentry traces or profiles: the healthcheck polled by load balancers and container orchestration every few
seconds.

Matched against the raw `PATH_INFO` before routing, so only exact static paths belong here. Any other path, including
an unknown one under the same prefix, is logged as normal.
"""

UNLOGGED_PATHS = frozenset({"/healthcheck"})


def is_unlogged_path(path: str) -> bool:
    return path in UNLOGGED_PATHS
