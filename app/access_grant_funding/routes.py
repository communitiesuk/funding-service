from uuid import UUID
from flask import Blueprint, abort, current_app, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import access_grant_funding_login_required, deliver_grant_funding_login_required, is_access_org_member
from app.common.data import interfaces
from app.common.data.types import RoleEnum

access_grant_funding_blueprint = Blueprint(name="access_grant_funding", import_name=__name__, url_prefix="/access")

@access_grant_funding_blueprint.route("/", methods=["GET"])
@access_grant_funding_login_required
def access_root() -> ResponseReturnValue:
    # if you have access to any grants, go to the first for now
    user = interfaces.user.get_current_user()

    if user.grant_recipients:
        return redirect(url_for("access_grant_funding.list_grants", organisation_id=user.grant_recipients[0].organisation.id))
    
    # TODO: this should just redirect or the select org page when that exists which could decide what
    #       to do with your session
    current_app.logger.error("Authorised user has no access to organisation or grants")
    
    # TODO: catch all error pages should account for if you're coming from AGF or DGF (likely based on how
    #       you authorised)
    return abort(403)

# TODO: propose unauthenticated requests to the service arrive at the access landing page
#       authenticated deliver users are routed to DGF, AGF to AGF (root unlikely in this file)
# TODO: base template should use MHCLG Grant Funding header
# TODO: decide between filtering orgs out of their access grants or doing a direct query
#       if access grants are going to be needed anyway it should be fine in terms of performance
@access_grant_funding_blueprint.route("/organisation/<uuid:organisation_id>/select-a-grant", methods=["GET"])

# TODO: this will be organisation specific and the interfaces will need to decide the balance
#       between using a grant recipient and using an organisation + grant
# @has_access_grant_role(RoleEnum.MEMBER)
@is_access_org_member
def list_grants(organisation_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    return render_template("access_grant_funding/grant_list.html", grants=user.access_grants)