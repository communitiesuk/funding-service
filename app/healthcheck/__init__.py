from flask import Blueprint, render_template

from app.common.data.services import create_grant
from app.extensions import db_request_session

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> str:
    return "OK"


@healthcheck_blueprint.route("/")
@db_request_session.db_request_auto_commit
def test_index_page() -> str:
    create_grant("A new grant")
    return render_template("common/base.html")
