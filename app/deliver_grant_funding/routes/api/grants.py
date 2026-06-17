import secrets

from flask import current_app, jsonify, request
from flask.typing import ResponseReturnValue

from app.common.data.interfaces.grants import get_active_grants
from app.deliver_grant_funding.routes.api import deliver_grant_funding_api_blueprint


@deliver_grant_funding_api_blueprint.get("/grants")
def list_active_grants() -> ResponseReturnValue:
    if (
        not request.authorization
        or not request.authorization.token
        or not secrets.compare_digest(
            request.authorization.token.encode(),
            current_app.config["JIRA_DATA_CONNECTOR_API_TOKEN"].encode(),
        )
    ):
        return jsonify(), 403

    grants = get_active_grants()
    grants_data = {
        "grants": [{"id": grant.code, "label": grant.name} for grant in grants]
        + [{"id": "not-listed", "label": "An other grant not listed"}],
    }

    return jsonify(grants_data), 200
