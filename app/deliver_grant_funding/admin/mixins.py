from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.user import get_current_user


class FlaskAdminPlatformAdminAccessibleMixin:
    def is_accessible(self) -> bool:
        return AuthorisationHelper.is_platform_admin(get_current_user())
