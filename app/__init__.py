from flask import Flask, Response, redirect, url_for
from flask.typing import ResponseReturnValue
from flask_babel import Babel
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader

from app import logging
from app.common.data import interfaces
from app.common.data.models import User
from app.config import get_settings
from app.extensions import (
    auto_commit_after_request,
    db,
    flask_assets_vite,
    login_manager,
    migrate,
    notification_service,
    talisman,
    toolbar,
)

# from app.sentry import init_sentry

# init_sentry()


def create_app() -> Flask:
    from app.common.data.base import BaseModel
    from flask_sqlalchemy_lite import _extension

    # Monkey patch to prevent app.teardown_appcontext(_close_async_sessions)
    def noop(*args, **kwargs):
        pass

    _extension._close_async_sessions = noop  # Override the function with a no-op

    app = Flask(__name__, static_folder="assets/dist/", static_url_path="/static")
    app.config.from_object(get_settings())

    # Initialise extensions
    logging.init_app(app)
    db.init_app(app)
    # auto_commit_after_request.init_app(app)

    # Attach routes
    from app.healthcheck import healthcheck_blueprint
    app.register_blueprint(healthcheck_blueprint)

    return app
