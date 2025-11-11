from flask import Blueprint

access_grant_funding_blueprint = Blueprint(name="access_grant_funding", import_name=__name__, url_prefix="/access")

from app.access_grant_funding.routes import (  # noqa: E402, F401
    misc,
    reports,
)
