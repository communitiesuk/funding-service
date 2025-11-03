from flask import Blueprint, current_app
from flask.typing import ResponseReturnValue
from sqlalchemy import text

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> ResponseReturnValue:
    return "OK", 200, {"content-type": "text/plain"}


@healthcheck_blueprint.route("/healthcheck/db")
def db_healthcheck_current_revision() -> ResponseReturnValue:
    try:
        db = current_app.extensions["sqlalchemy"]
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return result, 200, {"content-type": "text/plain"}
    except Exception:
        current_app.logger.exception("Database healthcheck error")
        return "ERROR", 500, {"content-type": "text/plain"}
