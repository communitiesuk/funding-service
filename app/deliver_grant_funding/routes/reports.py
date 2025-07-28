from uuid import UUID

from flask import render_template
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import has_grant_role
from app.common.data.interfaces.grants import get_grant
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/reports", methods=["GET"])
@has_grant_role(RoleEnum.MEMBER)
def list_reports(grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)
    return render_template("deliver_grant_funding/reports/list_reports.html", grant=grant)
