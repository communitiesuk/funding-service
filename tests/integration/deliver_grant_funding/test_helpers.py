from app.common.data.models import (
    Submission,
    SubmissionEvent,
)
from app.common.data.types import (
    SubmissionModeEnum,
)
from app.deliver_grant_funding.helpers import start_testing_submission
from tests.utils import AnyStringMatching


def test_start_testing_submission(authenticated_grant_admin_client, db_session, factories):
    user = authenticated_grant_admin_client.user
    collection = factories.collection.create(create_completed_submissions_each_question_type__test=1)

    for submission in collection.test_submissions:
        submission.created_by = user
        factories.submission_event.create(submission=submission, created_by=submission.created_by)

    old_test_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.TEST).all()
    old_submission_events_from_db = db_session.query(SubmissionEvent).all()

    assert len(old_test_submissions_from_db) == 1
    assert len(old_submission_events_from_db) == 1

    # Test that old submissions are deleted and you get redirected to the preview tasklist
    response = start_testing_submission(collection=collection)
    assert response.status_code == 302
    assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}$")
    test_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.TEST).all()
    assert len(test_submissions_from_db) == 1
    assert test_submissions_from_db[0].id is not old_test_submissions_from_db[0].id

    # When passing a form, test that old submissions are deleted and you get redirected to the specific
    # ask a question preview
    form = collection.forms[0]
    response = start_testing_submission(collection=collection, form=form)
    assert response.status_code == 302
    assert response.location == AnyStringMatching(
        "/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}/[a-z0-9-]{36}"
    )
    second_test_submissions_from_db = (
        db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.TEST).all()
    )
    assert len(second_test_submissions_from_db) == 1
    assert second_test_submissions_from_db[0].id not in [
        old_test_submissions_from_db[0].id,
        test_submissions_from_db[0].id,
    ]
