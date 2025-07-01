from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import is_platform_admin
from app.common.data import interfaces

developers_access_blueprint = Blueprint("access", __name__, url_prefix="/access")


@developers_access_blueprint.get("/grants")
@is_platform_admin
def grants_list() -> ResponseReturnValue:
    grants = interfaces.grants.get_all_grants_by_user(interfaces.user.get_current_user())
    return render_template("developers/access/index.html", grants=grants)
