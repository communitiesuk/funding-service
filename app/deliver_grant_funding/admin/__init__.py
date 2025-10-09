from flask_admin import Admin
from flask_sqlalchemy_lite import SQLAlchemy

from app.deliver_grant_funding.admin.entities import PlatformAdminUserView


def register_admin_views(flask_admin: Admin, db: SQLAlchemy) -> None:
    flask_admin.add_view(PlatformAdminUserView(db.session))
