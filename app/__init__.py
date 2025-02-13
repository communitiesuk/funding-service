from flask import Flask

from app.extensions import db, migrate


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object('app.config.Config')

    from app.healthcheck import healthcheck_blueprint

    app.register_blueprint(healthcheck_blueprint)

    db.init_app(app)
    migrate.init_app(app, db, directory='app/common/data/migrations', compare_type=True, render_as_batch=True)

    return app
