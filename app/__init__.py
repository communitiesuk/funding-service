from flask import Flask

from app import logging
from app.extensions import db, migrate, toolbar
from app.sentry import init_sentry

init_sentry()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    logging.init_app(app)
    db.init_app(app)
    migrate.init_app(
        app,
        db,  # type: ignore[arg-type]  # not natively compatible with Flask-SQLAlchemy-Lite; but is fine for us.
        directory="app/common/data/migrations",
        compare_type=True,
        render_as_batch=True,
    )
    toolbar.init_app(app)

    from app.healthcheck import healthcheck_blueprint

    app.register_blueprint(healthcheck_blueprint)

    return app
