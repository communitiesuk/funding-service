"""
Simple centralised registry for feature flags.

Flags should be added and removed from this registry as they are needed in the code base.

Feature flags can pull from:
- environment variables through Flask config
- contextual URL models like grant, organisation or grant recipient

Usage:
    from app.common.helpers.feature_flags import PRE_AWARD_FEATURES

    if PRE_AWARD_FEATURES.is_enabled:
        ...

    if bool(PRE_AWARD_FEATURES):
        ...
"""

from collections.abc import Callable

from flask import request

from app.common.data.interfaces.grants import get_grant


class FeatureFlag:
    def __init__(self, description: str, resolver: Callable[[], bool]) -> None:
        self.description = description
        self._resolver = resolver

    @property
    def is_enabled(self) -> bool:
        return self._resolver()

    def __bool__(self) -> bool:
        return self.is_enabled


# Features registry


def _check_grant_allows_pre_award() -> bool:
    grant_id = request.view_args.get("grant_id") if request.view_args else None
    if not grant_id:
        raise ValueError("grant_id required in URL for PRE_AWARD_FEATURES feature flag")
    return get_grant(grant_id).allow_pre_award


PRE_AWARD_FEATURES = FeatureFlag(
    description="Grant supports pre-award features",
    resolver=_check_grant_allows_pre_award,
)
