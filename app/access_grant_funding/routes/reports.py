from uuid import UUID

from flask import render_template
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import (
    is_access_org_member,
)
from app.common.data import interfaces


@access_grant_funding_blueprint.route("/organisation/<uuid:organisation_id>/grants", methods=["GET"])
@is_access_org_member
def list_grants(organisation_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grants = [
        grant_recipient.grant for grant_recipient in user.grant_recipients(limit_to_organisation_id=organisation_id)
    ]
    return render_template("access_grant_funding/grant_list.html", grants=grants)
