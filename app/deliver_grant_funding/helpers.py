import itertools
from typing import TYPE_CHECKING, Callable

from flask import current_app, jsonify, redirect, session, url_for
from flask.typing import ResponseReturnValue

from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_submission,
    delete_collection_preview_submissions_created_by_user,
    get_submissions_by_user,
)
from app.common.data.types import SubmissionModeEnum
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.forms import PreviewGuidanceForm
from app.deliver_grant_funding.types import PreviewGuidanceBadRequestResponse, PreviewGuidanceSuccessResponse
from app.extensions import s3_service

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form


def start_previewing_collection(collection: Collection, form: Form | None = None) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    file_prefixes_to_delete = [
        submission.s3_key_prefix
        for submission in get_submissions_by_user(
            user, collection_id=collection.id, submission_mode=SubmissionModeEnum.PREVIEW
        )
    ]

    delete_collection_preview_submissions_created_by_user(collection=collection, created_by_user=user)
    submission = create_submission(collection=collection, created_by=user, mode=SubmissionModeEnum.PREVIEW)
    helper = SubmissionHelper(submission)

    for file_prefix in file_prefixes_to_delete:
        s3_service.delete_prefix(file_prefix)

    # Pop this if it exists; sanity check for not terminating a session correctly
    session.pop("test_submission_form_id", None)
    if form:
        question = helper.get_first_question_for_form(form)
        if question:
            session["test_submission_form_id"] = form.id
            return redirect(
                url_for(
                    "deliver_grant_funding.ask_a_question",
                    grant_id=collection.grant_id,
                    submission_id=helper.submission.id,
                    question_id=question.id,
                )
            )

    return redirect(
        url_for(
            "deliver_grant_funding.submission_tasklist",
            grant_id=collection.grant_id,
            submission_id=helper.submission.id,
        )
    )


def preview_guidance_response(convert_guidance: Callable[[str], str]) -> ResponseReturnValue:
    """Validate a submitted PreviewGuidanceForm and return the converted guidance as a JSON response.

    The JSON contract is shared with the ajax-markdown-preview JS component. `convert_guidance` must return
    known-good (ie escaped) HTML suitable for inserting straight into the DOM.
    """
    form = PreviewGuidanceForm()
    if form.validate_on_submit():
        try:
            return jsonify(
                PreviewGuidanceSuccessResponse(guidance_html=convert_guidance(form.guidance.data or "")).model_dump(
                    mode="json"
                )
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
        PreviewGuidanceBadRequestResponse(errors=list(itertools.chain.from_iterable(form.errors.values()))).model_dump(
            mode="json"
        )
    ), 400
