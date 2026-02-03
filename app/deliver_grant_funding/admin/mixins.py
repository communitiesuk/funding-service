from typing import Any

from flask import abort
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import deliver_grant_funding_login_required
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import RoleEnum


class FlaskAdminPlatformAdminAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.is_platform_admin(get_current_user())

    @deliver_grant_funding_login_required
    def inaccessible_callback(self, *args: Any, **kwargs: Any) -> ResponseReturnValue:
        return abort(403)


class FlaskAdminPlatformAdminGrantLifecycleManagerAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.has_platform_admin_role(RoleEnum.GRANT_LIFECYCLE_MANAGER, get_current_user())

    @deliver_grant_funding_login_required
    def inaccessible_callback(self, *args: Any, **kwargs: Any) -> ResponseReturnValue:
        return abort(403)


class FlaskAdminPlatformAdminDataAnalystAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.has_platform_admin_role(RoleEnum.DATA_ANALYST, get_current_user())

    @deliver_grant_funding_login_required
    def inaccessible_callback(self, *args: Any, **kwargs: Any) -> ResponseReturnValue:
        return abort(403)


class FlaskAdminPlatformMemberAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.is_platform_member(get_current_user())

    @deliver_grant_funding_login_required
    def inaccessible_callback(self, *args: Any, **kwargs: Any) -> ResponseReturnValue:
        return abort(403)
