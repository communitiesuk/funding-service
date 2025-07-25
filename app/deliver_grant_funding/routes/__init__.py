from flask import Blueprint

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)

from app.deliver_grant_funding.routes import grant_details, grant_setup, grant_team, misc  # noqa: E402, F401
