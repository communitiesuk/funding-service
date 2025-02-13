from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    from app.healthcheck import healthcheck_blueprint

    app.register_blueprint(healthcheck_blueprint)

    return app
