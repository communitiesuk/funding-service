import uuid

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import is_platform_admin
from app.common.data import interfaces
from app.common.data.interfaces.grants import get_grant
from app.common.data.types import SubmissionStatusEnum

developers_access_blueprint = Blueprint("access", __name__, url_prefix="/access")


@developers_access_blueprint.get("/grants")
@is_platform_admin
def grants_list() -> ResponseReturnValue:
    grants = interfaces.grants.get_all_grants_by_user(interfaces.user.get_current_user())
    return render_template("developers/access/index.html", grants=grants)


# note: no auth decorator on this page, fully public, the template itself deals with varying the response based on
#       anonymous vs logged-in user.
@developers_access_blueprint.get("/grant/<uuid:grant_id>")
def grant_details(grant_id: uuid.UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id)
    # todo: feed submissions/submission_helpers into the template to render statuses
    return render_template(
        "developers/access/grant_details.html",
        grant=grant,
        statuses=SubmissionStatusEnum,
    )
