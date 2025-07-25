from uuid import UUID

from flask import abort, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import NoResultFound

from app.common.auth.decorators import has_grant_role, is_platform_admin
from app.common.data import interfaces
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.forms import GrantAddUserForm
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request, notification_service


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/users", methods=["GET"])
@has_grant_role(RoleEnum.MEMBER)
def list_users_for_grant(grant_id: UUID) -> ResponseReturnValue:
    try:
        grant = interfaces.grants.get_grant(grant_id)
    except NoResultFound:
        return abort(404)
    return render_template(
        "deliver_grant_funding/grant_team/grant_user_list.html",
        grant=grant,
        service_desk_url=current_app.config["SERVICE_DESK_URL"],
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/users/add", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def add_user_to_grant(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantAddUserForm(grant=grant)
    if form.validate_on_submit():
        if form.user_email.data:
            # are they already in this grant - if so, redirect to the list of users
            grant_user = next(
                (user for user in grant.users if user.email.lower() == form.user_email.data.lower()), None
            )
            if grant_user:
                return redirect(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant_id))
            interfaces.user.add_grant_member_role_or_create_invitation(email_address=form.user_email.data, grant=grant)
            notification_service.send_member_confirmation(
                grant=grant,
                email_address=form.user_email.data,
            )
            flash("We’ve emailed the grant team member a link to sign in")
            return redirect(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant_id))

    return render_template("deliver_grant_funding/grant_team/grant_user_add.html", form=form, grant=grant)
