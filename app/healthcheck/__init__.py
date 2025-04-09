from flask import Blueprint
from flask.typing import ResponseReturnValue

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> ResponseReturnValue:
    return "OK", 200, {"content-type": "text/plain"}
