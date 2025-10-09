from flask_admin import AdminIndexView

from app.deliver_grant_funding.admin.mixins import FlaskAdminPlatformAdminAccessibleMixin


class PlatformAdminIndexView(FlaskAdminPlatformAdminAccessibleMixin, AdminIndexView):
    pass
