from flask import Blueprint

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> str:
    return "OK"
