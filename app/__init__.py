from flask import Flask
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader

from app import logging
from app.extensions import db, migrate, toolbar, vite
from app.sentry import init_sentry

init_sentry()


def create_app() -> Flask:
    from app.common.data.base import BaseModel

    app = Flask(__name__, static_folder="vite/dist/assets/static", static_url_path="/static")
    app.config.from_object("app.config.Config")

    # Initialise extensions
    logging.init_app(app)
    db.init_app(app)
    migrate.init_app(
        app,
        db,  # type: ignore[arg-type]  # not natively compatible with Flask-SQLAlchemy-Lite; but is fine for us.
        directory="app/common/data/migrations",
        compare_type=True,
        render_as_batch=True,
        metadatas=BaseModel.metadata,
    )
    toolbar.init_app(app)
    vite.init_app(app)

    # FIXME: raise this bug on flask-vite and get it fixed
    app.route("/_vite/<path:filename>", endpoint="app/vite.static", host=vite.vite_routes_host)(vite.vite_static)

    # Configure templates
    app.jinja_loader = ChoiceLoader(
        [
            PackageLoader("app.common"),
            PrefixLoader({"govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja")}),
        ]
    )

    # Attach routes
    from app.healthcheck import healthcheck_blueprint

    app.register_blueprint(healthcheck_blueprint)

    return app
