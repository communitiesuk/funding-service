from typing import Any

from flask import abort
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import deliver_grant_funding_login_required
from app.common.data.interfaces.user import get_current_user


class FlaskAdminPlatformAdminAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.is_platform_admin(get_current_user())

    @deliver_grant_funding_login_required
    def inaccessible_callback(self, *args: Any, **kwargs: Any) -> ResponseReturnValue:
        return abort(403)


class FlaskAdminPlatformMemberAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.is_platform_member(get_current_user())

    @deliver_grant_funding_login_required
    def inaccessible_callback(self, *args: Any, **kwargs: Any) -> ResponseReturnValue:
        return abort(403)
