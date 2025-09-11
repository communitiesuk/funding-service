from flask import Blueprint

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__, url_prefix="/deliver")

from app.deliver_grant_funding.routes import (  # noqa: E402, F401
    grant_details,
    grant_setup,
    grant_team,
    misc,
    reports,
    runner,
)
