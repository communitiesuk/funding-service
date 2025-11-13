from uuid import UUID

from flask import abort, current_app, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import access_grant_funding_login_required, is_access_org_member
from app.common.data import interfaces
from app.common.data.interfaces.grants import get_grant


@access_grant_funding_blueprint.route("/", methods=["GET"])
@access_grant_funding_login_required
def index() -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    if grant_recipients := user.get_grant_recipients():
        return redirect(
            url_for("access_grant_funding.list_grants", organisation_id=grant_recipients[0].organisation.id)
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
        grant_recipient.grant for grant_recipient in user.get_grant_recipients(limit_to_organisation_id=organisation_id)
    ]
    return render_template("access_grant_funding/grant_list.html", grants=grants, organisation_id=organisation_id)


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grant/<uuid:grant_id>/select-a-report", methods=["GET"]
)
@is_access_org_member
def list_reports(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id=grant_id)
    if (
        organisation_id not in [gr.organisation_id for gr in grant.grant_recipients]
        or interfaces.user.get_current_user()
        not in next(gr for gr in grant.grant_recipients if gr.organisation_id == organisation_id).users
    ):
        return render_template("access_grant_funding/errors/organisation_is_not_grant_recipient.html"), 404

    return render_template(
        "access_grant_funding/report_list.html",
        reports=grant.access_reports,
        organisation_id=organisation_id,
        grant=grant,
    )
