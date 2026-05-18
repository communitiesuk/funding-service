"""
Simple centralised registry for feature flags.

Flags should be added and removed from this registry as they are needed in the code base.

Feature flags can pull from:
- environment variables through Flask config
- contextual URL models like grant, organisation or grant recipient

Usage in codebase:
    from app.common.helpers.feature_flags import FeatureFlags

    if FeatureFlags.PRE_AWARD.is_enabled:
        ...

    if bool(FeatureFlags.PRE_AWARD):
        ...

Usage in templates:
    {% if feature_flags.PRE_AWARD.is_enabled %}
        ...

    {% if feature_flags.PRE_AWARD %}
        ...
"""

from collections.abc import Callable

from flask import request

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user


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
        return False
    return get_grant(grant_id).allow_pre_award


def _check_user_is_platform_member() -> bool:
    return AuthorisationHelper.is_platform_member(get_current_user())


class FeatureFlags:
    PRE_AWARD = FeatureFlag(
        description="Grant supports pre-award features",
        resolver=_check_grant_allows_pre_award,
    )
    NEW_CONTEXT_SOURCES = FeatureFlag(
        description="Show new work in progress context sources",
        resolver=_check_user_is_platform_member,
    )
