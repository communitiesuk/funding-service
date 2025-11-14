from uuid import UUID

from flask import abort, current_app, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import (
    access_grant_funding_login_required,
    has_grant_recipient_member_role,
    is_access_org_member,
)
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_all_live_submissions_for_grant_recipient
from app.common.data.interfaces.grants import get_grant
from app.common.helpers.collections import SubmissionHelper


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
@has_grant_recipient_member_role
def list_reports(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id=grant_id)

    # TODO new get_grant_recipient by org and grant id
    # don't need to check, interface will 404 if not found

    # find grant_recipient for this user-org-grant
    # grant_recipient = next((gr for gr in grant.grant_recipients if gr.organisation_id == organisation_id), None)
    # if not grant_recipient or interfaces.user.get_current_user() not in grant_recipient.users:
    #     return render_template("access_grant_funding/errors/organisation_is_not_grant_recipient.html"), 404

    # use updated get_all_submissions_with_mode_for_collection_with_full_schema with restrict param

    grant_recipient = interfaces.user.current_user.get_grant_recipient(
        organisation_id=organisation_id, grant_id=grant_id
    )
    if not grant_recipient:
        return abort(404)

    submissions = [
        SubmissionHelper.load(submission.id)
        for submission in get_all_live_submissions_for_grant_recipient(
            grant_id=grant_id, grant_recipient_id=grant_recipient.id
        )
    ]
    return render_template(
        "access_grant_funding/report_list.html",
        reports=grant.access_reports,
        organisation_id=organisation_id,
        grant=grant,
        submissions=submissions,
    )
