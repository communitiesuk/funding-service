try:
    from flask_debugtoolbar import DebugToolbarExtension
except ImportError:
    DebugToolbarExtension = None  # type: ignore[misc, assignment]
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from flask_talisman import Talisman

from app.extensions.auto_commit_after_request import AutoCommitAfterRequestExtension
from app.extensions.flask_assets_vite import FlaskAssetsViteExtension
from app.extensions.record_sqlalchemy_queries import RecordSqlalchemyQueriesExtension
from app.services.notify import NotificationService

db = SQLAlchemy()
auto_commit_after_request = AutoCommitAfterRequestExtension(db=db)
migrate = Migrate()
toolbar = DebugToolbarExtension() if DebugToolbarExtension is not None else None
notification_service = NotificationService()
talisman = Talisman()
flask_assets_vite = FlaskAssetsViteExtension()
login_manager = LoginManager()
record_sqlalchemy_queries = RecordSqlalchemyQueriesExtension()

__all__ = [
    "db",
    "auto_commit_after_request",
    "migrate",
    "toolbar",
    "notification_service",
    "talisman",
    "flask_assets_vite",
    "login_manager",
    "record_sqlalchemy_queries",
]
