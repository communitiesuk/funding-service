import itertools
from uuid import UUID

from flask import Blueprint, current_app, jsonify
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.user import get_current_user
from app.deliver_grant_funding.forms import PreviewGuidanceForm
from app.deliver_grant_funding.types import (
    PreviewGuidanceBadRequestResponse,
    PreviewGuidanceSuccessResponse,
    PreviewGuidanceUnauthorisedResponse,
)

deliver_grant_funding_api_blueprint = Blueprint("api", __name__)


@deliver_grant_funding_api_blueprint.post("/api/v1/<uuid:grant_id>/preview-guidance")
def preview_guidance(grant_id: UUID) -> ResponseReturnValue:
    if not AuthorisationHelper.is_deliver_grant_funding_user(get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    if not AuthorisationHelper.is_grant_member(grant_id, get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    form = PreviewGuidanceForm()
    if form.validate_on_submit():
        return jsonify(
            PreviewGuidanceSuccessResponse(
                guidance_html=current_app.extensions["govuk_markdown"].convert(form.guidance.data)
            ).model_dump(mode="json")
        ), 200

    return jsonify(
        PreviewGuidanceBadRequestResponse(
            errors=[error for error in itertools.chain.from_iterable(form.errors.values())]
        ).model_dump(mode="json")
    ), 400
