from typing import TYPE_CHECKING
from uuid import UUID

from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import is_platform_admin
from app.common.data import interfaces
from app.common.data.interfaces.temporary import (
    delete_grant,
)
from app.common.data.interfaces.user import add_permissions_to_user, get_current_user, remove_permissions_from_user
from app.common.data.types import (
    RoleEnum,
)
from app.developers.forms import (
    BecomeGrantTeamMemberForm,
    ConfirmDeletionForm,
)
from app.extensions import auto_commit_after_request

if TYPE_CHECKING:
    pass


developers_deliver_blueprint = Blueprint("deliver", __name__, url_prefix="/deliver")


@developers_deliver_blueprint.route("/grants/<uuid:grant_id>", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def grant_developers(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    confirm_deletion_form = ConfirmDeletionForm()
    become_grant_team_member_form = BecomeGrantTeamMemberForm()
    if (
        "delete_grant" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_grant(grant_id=grant.id)
        return redirect(url_for("deliver_grant_funding.list_grants"))

    if become_grant_team_member_form.validate_on_submit():
        user = get_current_user()
        remove_permissions_from_user(user=user, permissions=[RoleEnum.ADMIN, RoleEnum.MEMBER])
        add_permissions_to_user(
            user, permissions=[RoleEnum.MEMBER], organisation_id=grant.organisation_id, grant_id=grant.id
        )
        return redirect(url_for("deliver_grant_funding.grant_homepage", grant_id=grant.id))

    return render_template(
        "developers/deliver/grant_developers.html",
        grant=grant,
        confirm_deletion_form=confirm_deletion_form,
        become_grant_team_member_form=become_grant_team_member_form,
        delete_grant="delete_grant" in request.args,
    )
