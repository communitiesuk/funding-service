from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> ResponseReturnValue:
    return "OK", 200, {"content-type": "text/plain"}


@healthcheck_blueprint.route("/")
def test_index_page() -> str:
    return render_template("common/base.html")
