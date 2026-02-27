from typing import TYPE_CHECKING

from flask import redirect, session, url_for
from flask.typing import ResponseReturnValue

from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_submission,
    delete_collection_preview_submissions_created_by_user,
    get_submissions_by_user,
)
from app.common.data.types import SubmissionModeEnum
from app.common.helpers.collections import SubmissionHelper
from app.extensions import s3_service

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form


def start_previewing_collection(collection: Collection, form: Form | None = None) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    for submission in get_submissions_by_user(
        user, collection_id=collection.id, submission_mode=SubmissionModeEnum.PREVIEW
    ):
        helper = SubmissionHelper(submission)
        s3_service.delete_prefix(helper.submission.s3_key_prefix)

    delete_collection_preview_submissions_created_by_user(collection=collection, created_by_user=user)
    submission = create_submission(collection=collection, created_by=user, mode=SubmissionModeEnum.PREVIEW)
    helper = SubmissionHelper(submission)

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
