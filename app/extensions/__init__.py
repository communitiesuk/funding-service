from flask_debugtoolbar import DebugToolbarExtension
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from flask_talisman import Talisman

from app.extensions.auto_commit_after_request import AutoCommitAfterRequestExtension
from app.extensions.flask_assets_vite import FlaskAssetsViteExtension
from app.services.notify import NotificationService

db = SQLAlchemy()
auto_commit_after_request = AutoCommitAfterRequestExtension(db=db)
migrate = Migrate()
toolbar = DebugToolbarExtension()
notification_service = NotificationService()
talisman = Talisman()
flask_assets_vite = FlaskAssetsViteExtension()

__all__ = [
    "db",
    "auto_commit_after_request",
    "migrate",
    "toolbar",
    "notification_service",
    "talisman",
    "flask_assets_vite",
]
