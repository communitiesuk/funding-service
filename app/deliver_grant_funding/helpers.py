from typing import TYPE_CHECKING, Optional

from flask import redirect, session, url_for
from flask.typing import ResponseReturnValue

from app.common.data import interfaces
from app.common.data.interfaces.collections import create_submission, delete_collection_test_submissions_created_by_user
from app.common.data.types import SubmissionModeEnum
from app.common.helpers.collections import SubmissionHelper

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form


def start_testing_submission(collection: "Collection", form: Optional["Form"] = None) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    delete_collection_test_submissions_created_by_user(collection=collection, created_by_user=user)
    submission = create_submission(collection=collection, created_by=user, mode=SubmissionModeEnum.TEST)
    helper = SubmissionHelper(submission)

    # Pop this if it exists; sanity check for not terminating a session correctly
    session.pop("test_submission_form_id", None)
    if form:
        question = helper.get_first_question_for_form(form)
        if not question:
            raise RuntimeError("Form with no question")

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
