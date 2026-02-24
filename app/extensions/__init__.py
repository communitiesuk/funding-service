from flask import Flask
from flask_login import LoginManager, user_logged_in
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from flask_talisman import Talisman

from app.common.data.models_user import User
from app.common.markdown import FlaskGOVUKMarkdown
from app.extensions.auto_commit_after_request import AutoCommitAfterRequestExtension
from app.extensions.flask_assets_vite import FlaskAssetsViteExtension
from app.extensions.record_sqlalchemy_queries import RecordSqlalchemyQueriesExtension
from app.services.notify import NotificationService
from app.services.s3 import S3Service

db = SQLAlchemy(engine_options={"echo": False})
auto_commit_after_request = AutoCommitAfterRequestExtension(db=db)
migrate = Migrate()
notification_service = NotificationService()
s3_service = S3Service()
talisman = Talisman()
flask_assets_vite = FlaskAssetsViteExtension()
login_manager = LoginManager()
record_sqlalchemy_queries = RecordSqlalchemyQueriesExtension()
govuk_markdown = FlaskGOVUKMarkdown()

try:
    from flask_debugtoolbar import DebugToolbarExtension

    toolbar = DebugToolbarExtension()
except ModuleNotFoundError:
    toolbar = None  # type: ignore[assignment]


def register_signals(app: Flask) -> None:
    @user_logged_in.connect_via(app)  # type: ignore[untyped-decorator]
    def user_logged_in_signal(sender: Flask, user: User) -> None:
        # This needs to be imported within the function to avoid a circular import with the `db` extension
        from app.common.data.interfaces.user import set_user_last_logged_in_at_utc

        set_user_last_logged_in_at_utc(user)


__all__ = [
    "db",
    "auto_commit_after_request",
    "migrate",
    "toolbar",
    "notification_service",
    "s3_service",
    "talisman",
    "flask_assets_vite",
    "login_manager",
    "record_sqlalchemy_queries",
    "register_signals",
]
