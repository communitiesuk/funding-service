from flask import Blueprint

deliver_grant_funding_api_blueprint = Blueprint("api", __name__, url_prefix="/api/v1")

from app.deliver_grant_funding.routes.api import callbacks, grants, guidance  # noqa: E402, F401
