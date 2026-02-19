import itertools
from uuid import UUID

from flask import Blueprint, current_app, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from werkzeug.datastructures import MultiDict

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.collections.forms import build_question_form
from app.common.collections.preview import PreviewQuestion, PreviewRunner
from app.common.data.interfaces.collections import get_collection, get_form_by_id, get_question_by_id
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.forms import PreviewGuidanceForm
from app.deliver_grant_funding.types import (
    PreviewGuidanceBadRequestResponse,
    PreviewGuidanceSuccessResponse,
    PreviewGuidanceUnauthorisedResponse,
    PreviewQuestionBadRequestResponse,
    PreviewQuestionSuccessResponse,
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
    if not AuthorisationHelper.is_deliver_grant_member(collection.grant_id, get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    form = PreviewGuidanceForm()
    if form.validate_on_submit():
        interpolate = SubmissionHelper.get_interpolator(collection)

        try:
            # NOTE: `interpolate(with_interpolation_highlighting=True)` returns HTML that must be known-good
            #       (ie escaped) suitable for inserting straight into the DOM.
            return jsonify(
                PreviewGuidanceSuccessResponse(
                    guidance_html=interpolate(
                        current_app.extensions["govuk_markdown"].convert(form.guidance.data),
                        with_interpolation_highlighting=True,  # type: ignore[call-arg]
                    )
                ).model_dump(mode="json")
            ), 200
        except SyntaxError:
            current_app.logger.warning(
                "Guidance contains invalid syntax %(guidance_text)s",
                {"guidance_text": form.guidance.data},
            )
            return jsonify(
                PreviewGuidanceBadRequestResponse(errors=["Guidance contains invalid syntax"]).model_dump(mode="json")
            ), 400
    return jsonify(
        PreviewGuidanceBadRequestResponse(
            errors=[error for error in itertools.chain.from_iterable(form.errors.values())]
        ).model_dump(mode="json")
    ), 400


@deliver_grant_funding_api_blueprint.post("/api/v1/<uuid:collection_id>/preview-question")
def preview_question(collection_id: UUID) -> ResponseReturnValue:
    """
    This endpoint takes question form data and returns rendered HTML showing how the question will appear
    to a grant recipient. It builds a lightweight in-memory question object and renders it using the same
    rendering pipeline as the form runner, without any database writes.
    """
    if not AuthorisationHelper.is_deliver_grant_funding_user(get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    collection = get_collection(collection_id)
    if not AuthorisationHelper.is_deliver_grant_member(collection.grant_id, get_current_user()):
        return jsonify(PreviewGuidanceUnauthorisedResponse().model_dump(mode="json")), 401

    data = request.get_json(silent=True)
    if not data or not data.get("data_type") or not data.get("text"):
        return jsonify(
            PreviewQuestionBadRequestResponse(errors=["Question text and data type are required"]).model_dump(
                mode="json"
            )
        ), 400

    try:
        data_type = QuestionDataType.coerce(data["data_type"])
    except (ValueError, KeyError):
        return jsonify(
            PreviewQuestionBadRequestResponse(errors=["Invalid question data type"]).model_dump(mode="json")
        ), 400

    # Parse data source items from newline-separated string
    raw_items = data.get("data_source_items", "")
    data_source_items = [item.strip() for item in raw_items.split("\n") if item.strip()] if raw_items else None

    # For edit case, load existing guidance and validations from the DB question
    guidance_heading = None
    guidance_body = None
    validations = []
    question_id = data.get("question_id")
    if question_id:
        try:
            db_question = get_question_by_id(UUID(question_id))
            guidance_heading = db_question.guidance_heading
            guidance_body = db_question.guidance_body
            validations = db_question.validations
        except Exception:
            pass

    preview_q = PreviewQuestion.from_form_data(
        data_type=data_type,
        text=data.get("text", ""),
        hint=data.get("hint"),
        name=data.get("name", ""),
        rows=int(data["rows"]) if data.get("rows") else None,
        word_limit=int(data["word_limit"]) if data.get("word_limit") else None,
        prefix=data.get("prefix"),
        suffix=data.get("suffix"),
        width=data.get("width"),
        number_type=data.get("number_type"),
        max_decimal_places=int(data["max_decimal_places"]) if data.get("max_decimal_places") else None,
        data_source_items=data_source_items,
        separate_option_if_no_items_match=bool(data.get("separate_option_if_no_items_match")),
        none_of_the_above_item_text=data.get("none_of_the_above_item_text"),
        approximate_date=bool(data.get("approximate_date")),
        guidance_heading=guidance_heading,
        guidance_body=guidance_body,
        validations=validations,
        question_id=UUID(question_id) if question_id else None,
    )

    interpolate = SubmissionHelper.get_interpolator(collection)
    interpolation_context = ExpressionContext.build_expression_context(collection=collection, mode="interpolation")

    answer = data.get("answer")
    formdata = None
    if answer is not None:
        if data_type == QuestionDataType.DATE and isinstance(answer, list):
            formdata = MultiDict([(preview_q.safe_qid, v) for v in answer])
        elif data_type == QuestionDataType.CHECKBOXES and isinstance(answer, list):
            formdata = MultiDict([(preview_q.safe_qid, v) for v in answer])
        else:
            formdata = MultiDict({preview_q.safe_qid: answer})

    QuestionForm = build_question_form(
        questions=[preview_q],
        evaluation_context=ExpressionContext(),
        interpolation_context=interpolation_context,
    )

    question_form = QuestionForm(formdata=formdata, meta={"csrf": False}) if formdata is not None else QuestionForm()

    if formdata is not None:
        question_form.validate()
    elif data_type == QuestionDataType.DATE:
        # For date fields, the GOV.UK widget expects raw_data to be a list of 3 items (day, month, year).
        # When instantiating a form without submission data, raw_data is None which causes an unpacking error.
        date_field = question_form.get_question_field(preview_q)
        date_field.raw_data = ["", "", ""]

    # Build caption from form title if available
    form_id = data.get("form_id")
    caption = ""
    if form_id:
        try:
            db_form = get_form_by_id(UUID(form_id))
            caption = db_form.title
        except Exception:
            pass

    runner = PreviewRunner(
        component=preview_q,
        question_form=question_form,
        question_page_caption=caption,
        question_page_heading=preview_q.guidance_heading,
        _interpolate=interpolate,
    )

    question_html = render_template(
        "deliver_grant_funding/partials/_question_preview.html",
        runner=runner,
        form=question_form,
    )

    return jsonify(PreviewQuestionSuccessResponse(question_html=question_html).model_dump(mode="json")), 200
