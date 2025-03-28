from flask import Blueprint, render_template

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> str:
    return "OK"


@healthcheck_blueprint.route("/")
def test_index_page() -> str:
    return render_template("common/base.html")
