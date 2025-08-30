from uuid import UUID

from flask import flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from werkzeug import Response

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import is_mhclg_user
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection, get_form_by_id
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.types import FlashMessageType


@deliver_grant_funding_blueprint.route("/grants", methods=["GET"])
@is_mhclg_user
def list_grants() -> Response | str:
    user = interfaces.user.get_current_user()
    grants = interfaces.grants.get_all_grants_by_user(user=user)
    # TODO if the user is a MEMBER and does not have any grant we need to handle that but if you are a
    #  ADMIN then should be able to see grants or empty page with create grant feature
    if len(grants) == 1 and not AuthorisationHelper.is_platform_admin(user):
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grants[0].id))
    return render_template("deliver_grant_funding/grant_list.html", grants=grants)


@deliver_grant_funding_blueprint.get("/_internal/redirect-after-test-submission/<uuid:collection_id>")
def return_from_test_submission(collection_id: UUID) -> ResponseReturnValue:
    finished = "finished" in request.args

    if form_id := session.pop("test_submission_form_id", None):
        if finished:
            flash("You’ve been returned to the task builder", FlashMessageType.SUBMISSION_TESTING_COMPLETE.value)

        form = get_form_by_id(form_id)
        return redirect(
            url_for(
                "deliver_grant_funding.list_task_questions",
                grant_id=form.collection.grant.id,
                form_id=form_id,
            )
        )

    if finished:
        flash("You’ve been returned to the form builder", FlashMessageType.SUBMISSION_TESTING_COMPLETE.value)

    collection = get_collection(collection_id)
    return redirect(
        url_for("deliver_grant_funding.list_report_tasks", grant_id=collection.grant.id, report_id=collection.id)
    )
