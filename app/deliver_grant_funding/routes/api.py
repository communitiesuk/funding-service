import itertools
from uuid import UUID

from flask import Blueprint, current_app, jsonify
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.collections import get_collection
from app.common.data.interfaces.user import get_current_user
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.forms import PreviewGuidanceForm
from app.deliver_grant_funding.types import (
    PreviewGuidanceBadRequestResponse,
    PreviewGuidanceSuccessResponse,
    PreviewGuidanceUnauthorisedResponse,
)

deliver_grant_funding_api_blueprint = Blueprint("api", __name__)


@deliver_grant_funding_api_blueprint.post("/api/v1/<uuid:collection_id>/preview-guidance")
def preview_guidance(collection_id: UUID) -> ResponseReturnValue:
    """
    This endpoint takes some arbitrary guidance and returns HTML suitable for inserting into the DOM by our
    ajax-markdown-preview component. Our markdown converter will escape user input, and our interpolator will then
    insert highlighting spans into that escaped HTML to provide both safety from user input injection vulnerabilities,
    and highlighting of data references.
    """
    if not AuthorisationHelper.is_deliver_grant_funding_user(get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    collection = get_collection(collection_id)
    if not AuthorisationHelper.is_grant_member(collection.grant_id, get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    form = PreviewGuidanceForm()
    if form.validate_on_submit():
        interpolate = SubmissionHelper.get_interpolator(collection)

        # NOTE: `interpolate(with_interpolation_highlighting=True)` returns HTML that must be known-good (ie escaped)
        #       suitable for inserting straight into the DOM.
        return jsonify(
            PreviewGuidanceSuccessResponse(
                guidance_html=interpolate(
                    current_app.extensions["govuk_markdown"].convert(form.guidance.data),
                    with_interpolation_highlighting=True,  # type: ignore[call-arg]
                )
            ).model_dump(mode="json")
        ), 200

    return jsonify(
        PreviewGuidanceBadRequestResponse(
            errors=[error for error in itertools.chain.from_iterable(form.errors.values())]
        ).model_dump(mode="json")
    ), 400
