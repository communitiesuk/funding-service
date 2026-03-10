from uuid import UUID

from flask import render_template
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import has_access_grant_role
from app.common.data.interfaces.collections import get_all_submissions_with_mode_for_collection
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import RoleEnum
from app.common.helpers.collections import SubmissionHelper


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/award", methods=["GET"]
)
@has_access_grant_role(RoleEnum.MEMBER)
def list_award_collections(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)
    user = get_current_user()

    award_collections = grant_recipient.grant.get_access_award_collections_for_user(
        user, user_organisation=grant_recipient.organisation
    )

    submissions = []
    for collection in award_collections:
        submissions.extend(
            [
                SubmissionHelper(submission=submission)
                for submission in get_all_submissions_with_mode_for_collection(
                    collection_id=collection.id,
                    submission_mode=grant_recipient.submission_mode,
                    grant_recipient_ids=[grant_recipient.id],
                )
            ]
        )

    return render_template(
        "access_grant_funding/award_list.html",
        award_collections=award_collections,
        organisation_id=organisation_id,
        grant=grant_recipient.grant,
        submissions=submissions,
        grant_recipient=grant_recipient,
    )
