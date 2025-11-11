from uuid import UUID

from flask import Blueprint, abort, current_app, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import (
    access_grant_funding_login_required,
    is_access_org_member,
)
from app.common.data import interfaces

access_grant_funding_blueprint = Blueprint(name="access_grant_funding", import_name=__name__, url_prefix="/access")


@access_grant_funding_blueprint.route("/", methods=["GET"])
@access_grant_funding_login_required
def index() -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    if user.grant_recipients():
        return redirect(
            url_for("access_grant_funding.list_grants", organisation_id=user.grant_recipients()[0].organisation.id)
        )

    # TODO: this should just redirect or the select org page when that exists which could decide what
    #       to do with your session
    current_app.logger.error("Authorised user has no access to organisation or grants")
    return abort(403)


@access_grant_funding_blueprint.route("/organisation/<uuid:organisation_id>/grants", methods=["GET"])
@is_access_org_member
def list_grants(organisation_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grants = [
        grant_recipient.grant for grant_recipient in user.grant_recipients(limit_to_organisation_id=organisation_id)
    ]
    return render_template("access_grant_funding/grant_list.html", grants=grants)
