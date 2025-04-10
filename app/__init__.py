import json
from typing import Dict, Optional

from flask import Flask, current_app, redirect, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import Babel
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader
from pydantic import BaseModel as PydanticBaseModel
from pydantic import RootModel

from app import logging
from app.config import get_settings
from app.extensions import auto_commit_after_request, db, migrate, notification_service, toolbar
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
    toolbar.init_app(app)
    notification_service.init_app(app)

    # This section is needed for url_for("foo", _external=True) to
    # automatically generate http scheme when this sample is
    # running on localhost, and to generate https scheme when it is
    # deployed behind reversed proxy.
    # See also #proxy_setups section at
    # flask.palletsprojects.com/en/1.0.x/deploying/wsgi-standalone
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=app.config["PROXY_FIX_PROTO"], x_host=app.config["PROXY_FIX_HOST"])

    @app.before_request
    def log_x_forwarded_headers():
        current_app.logger.info("X-Forwarded Headers %(url)s:", dict(url=request.url))
        current_app.logger.info("%(environ)s", dict(environ=str(request.environ)))
        for header_name, header_value in request.headers.items():
            if header_name.lower().startswith("x-forwarded"):
                current_app.logger.info("  %(header)s: %(value)s", dict(header=header_name, value=header_value))

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

    class Asset(PydanticBaseModel):
        file: str
        name: Optional[str] = None
        src: str
        isEntry: bool

    class Manifest(RootModel[Optional[Dict[str, Asset]]]):
        root: Optional[Dict[str, Asset]]

        def __getitem__(self, item: str) -> Asset | None:
            # the type signature makes it _seem_ like it will safely handle a key error but it won't
            return self.root[item] if self.root else None

    # this will move out to a tiny extension that will configure the app to do this
    @app.context_processor
    def assets_processor():  # type: ignore[no-untyped-def]
        def vite_asset(relative_file_path: str) -> str:
            """
            Point assets at a vite development server while running locally
            to enable hot module replacement and automatic udpates to both SCSS
            and JavaScript.
            """

            if app.config["ASSETS_VITE_LIVE_ENABLED"]:
                return f"{app.config['ASSETS_VITE_BASE_URL']}/static/{relative_file_path}"

            try:
                with open("app/assets/dist/manifest.json", "r") as f:
                    data = json.load(f)
                    manifest = Manifest(**data)
                    known_asset = manifest[relative_file_path]
                    if known_asset:
                        return url_for("static", filename=known_asset.file)
            except (FileNotFoundError, KeyError):
                pass

            return url_for("static", filename=relative_file_path)

        return dict(vite_asset=vite_asset)

    return app
