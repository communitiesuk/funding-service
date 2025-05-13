import app.common.forms.question_service as question_service
from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for

__all__ = ["question_service"]

from app.common.data.interfaces.collections import add_data
from app.extensions import auto_commit_after_request

test_blueprint = Blueprint(
    "test",
    __name__,
    url_prefix="/",
)


@test_blueprint.route("/test", methods=["GET"])
@auto_commit_after_request
def request_a_link_to_sign_in():
    add_data()
    return "DONE"
