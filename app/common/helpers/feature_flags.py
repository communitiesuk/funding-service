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

from abc import ABC, abstractmethod

from flask import request, session
from flask.sessions import SessionMixin

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user


class FeatureFlagBase(ABC):
    # A description of what feature this flag is for
    description: str

    # A description of how the resolver decides who sees this feature
    resolver_description: str

    # Does this resolver need to read context from the specific request to decide if it's enabled or not? eg a URL
    # param
    uses_request_context: bool

    # Used for the SessionFeatureFlag base class; says that this feature flag can be toggled on or off manually
    # to see both sides.
    is_session_based: bool

    # An auto-assigned attribute tracking the name of the class variable this feature flag is related to on the
    # FeatureFlags class.
    name: str

    @property
    @abstractmethod
    def is_enabled(self) -> bool: ...

    def __bool__(self) -> bool:
        return self.is_enabled

    def __set_name__(self, owner, name):
        self.name = name


class StaticFeatureFlag(FeatureFlagBase):
    is_session_based = False

    @classmethod
    @abstractmethod
    def resolve(cls) -> bool: ...

    @property
    def is_enabled(self) -> bool:
        return self.resolve()


class SessionFeatureFlag(FeatureFlagBase):
    uses_request_context = False
    is_session_based = True

    @classmethod
    def resolve(cls, session_: SessionMixin, name: str) -> bool:
        return session_.get(name) is not None

    @property
    def is_enabled(self) -> bool:
        return self.resolve(session, self.name)

    def toggle(self) -> None:
        if self.name in session:
            session.pop(self.name)
            return

        session[self.name] = "on"


class PreAwardGrantFeatureFlag(StaticFeatureFlag):
    description = "Enables pre-award functionality for grants, giving access to applications and similar forms."
    resolver_description = "Determined by the `allow_pre_award` setting on each grant"
    uses_request_context = True

    @classmethod
    def resolve(cls) -> bool:
        grant_id = request.view_args.get("grant_id") if request.view_args else None
        if not grant_id:
            return False
        return get_grant(grant_id).allow_pre_award


class NewContextSourcesFeatureFlag(StaticFeatureFlag):
    description = "Shows new context sources for referencing data in collections"
    resolver_description = "Enabled when the current user is a platform member"
    uses_request_context = False

    @classmethod
    def resolve(cls) -> bool:
        return AuthorisationHelper.is_platform_member(get_current_user())


class NewChangeRequestFeatureFlag(SessionFeatureFlag):
    description = "Use the new change request workflow in Access and Deliver"


class FeatureFlags:
    PRE_AWARD = PreAwardGrantFeatureFlag()
    NEW_CONTEXT_SOURCES = NewContextSourcesFeatureFlag()
    NEW_CHANGE_REQUESTS = NewChangeRequestFeatureFlag()

    @classmethod
    def all(cls) -> list[FeatureFlagBase]:
        return [value for value in vars(cls).values() if isinstance(value, FeatureFlagBase)]
