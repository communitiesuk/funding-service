from flask import abort, current_app, redirect, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import access_grant_funding_login_required
from app.common.data import interfaces


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
