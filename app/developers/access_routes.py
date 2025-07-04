import uuid

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import is_platform_admin
from app.common.data import interfaces
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.temporary import get_submission_by_collection_and_user
from app.common.data.types import SubmissionStatusEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper

developers_access_blueprint = Blueprint("access", __name__, url_prefix="/access")


@developers_access_blueprint.get("/grants")
@is_platform_admin
def grants_list() -> ResponseReturnValue:
    grants = interfaces.grants.get_all_grants_by_user(interfaces.user.get_current_user())
    return render_template("developers/access/grants_list.html", grants=grants)


# note: no auth decorator on this page, fully public, the template itself deals with varying the response based on
#       anonymous vs logged-in user.
@developers_access_blueprint.route("/grants/<uuid:grant_id>", methods=["GET", "POST"])
def grant_details(grant_id: uuid.UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id)
    current_user = interfaces.user.get_current_user()

    form = GenericSubmitForm()
    if form.validate_on_submit():
        session["next"] = request.full_path
        return redirect(url_for("auth.request_a_link_to_sign_in"))

    submission_helpers = {}
    if current_user.is_authenticated:
        submission_helpers = {
            collection.id: SubmissionHelper.load(submission.id)
            for collection in grant.collections
            if (submission := get_submission_by_collection_and_user(collection, interfaces.user.get_current_user()))
        }

    return render_template(
        "developers/access/grant_details.html",
        grant=grant,
        statuses=SubmissionStatusEnum,
        submission_helpers=submission_helpers,
        form=form,
    )
