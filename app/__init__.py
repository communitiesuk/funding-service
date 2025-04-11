from flask import Flask, redirect, url_for
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
from app.sentry import init_sentry

init_sentry()


def create_app() -> Flask:
    from app.common.data.base import BaseModel

    app = Flask(__name__, static_folder="assets/dist/", static_url_path="/static")
    app.config.from_object(get_settings())

    # Initialise extensions
    logging.init_app(app)
    db.init_app(app)
    auto_commit_after_request.init_app(app)
    migrate.init_app(
        app,
        db,  # type: ignore[arg-type]  # not natively compatible with Flask-SQLAlchemy-Lite; but is fine for us.
        directory="app/common/data/migrations",
        compare_type=True,
        render_as_batch=True,
        metadatas=BaseModel.metadata,
    )
    flask_assets_vite.init_app(app)
    toolbar.init_app(app)
    notification_service.init_app(app)
    talisman.init_app(app, **app.config["TALISMAN_SETTINGS"])
    login_manager.init_app(app)

    @login_manager.user_loader  # type: ignore[misc]
    def load_user(user_id: str) -> User | None:
        return interfaces.user.get_user(user_id)

    # This section is needed for url_for("foo", _external=True) to
    # automatically generate http scheme when this sample is
    # running on localhost, and to generate https scheme when it is
    # deployed behind reversed proxy.
    # See also #proxy_setups section at
    # flask.palletsprojects.com/en/1.0.x/deploying/wsgi-standalone
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = (  # type: ignore[method-assign]
        ProxyFix(app.wsgi_app, x_proto=app.config["PROXY_FIX_PROTO"], x_host=app.config["PROXY_FIX_HOST"])
    )

    # Configure templates
    app.jinja_loader = ChoiceLoader(
        [
            PackageLoader("app.common"),
            PackageLoader("app.platform"),
            PrefixLoader({"govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja")}),
            PrefixLoader({"govuk_frontend_wtf": PackageLoader("govuk_frontend_wtf")}),
        ]
    )
    WTFormsHelpers(app)

    Babel(app)
    app.jinja_env.add_extension("jinja2.ext.i18n")

    # Attach routes
    from app.common.auth import auth_blueprint
    from app.healthcheck import healthcheck_blueprint
    from app.platform import platform_blueprint

    app.register_blueprint(healthcheck_blueprint)
    app.register_blueprint(platform_blueprint)
    app.register_blueprint(auth_blueprint)

    @app.route("/", methods=["GET"])
    def index() -> ResponseReturnValue:
        return redirect(url_for("platform.list_grants"))

    # when developing we want the toolbar assets to not cause the page to flicker
    # otherwise we don't want the server to continually 304 on assets the browser has
    # should make an intentional decision for when to be setting this
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

    return app
