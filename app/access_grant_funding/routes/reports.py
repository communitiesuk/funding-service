from uuid import UUID

from flask import redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import has_access_grant_role
from app.common.data.interfaces.collections import get_all_submissions_with_mode_for_collection_with_full_schema
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.types import RoleEnum, SubmissionModeEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports", methods=["GET"]
)
@has_access_grant_role(RoleEnum.MEMBER)
def list_reports(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)

    # TODO refactor when we persist the collection status and/or implement multiple rounds
    submissions = []
    for report in grant_recipient.grant.access_reports:
        submissions.extend(
            [
                SubmissionHelper(submission=submission)
                for submission in get_all_submissions_with_mode_for_collection_with_full_schema(
                    collection_id=report.id,
                    submission_mode=SubmissionModeEnum.LIVE,
                    grant_recipient_id=grant_recipient.id,
                )
            ]
        )

    return render_template(
        "access_grant_funding/report_list.html",
        reports=grant_recipient.grant.access_reports,
        organisation_id=organisation_id,
        grant=grant_recipient.grant,
        submissions=submissions,
        grant_recipient=grant_recipient,
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/view",
    methods=["GET", "POST"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def view_locked_report(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)

    submission = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)

    if not submission.is_locked_state:
        # note we're not redirecting to the route to submission as you might have been directed from
        # there, go somewhere we know will load consistently and the user can step back in
        return redirect(
            url_for("access_grant_funding.list_reports", organisation_id=organisation_id, grant_id=grant_id)
        )

    form = GenericSubmitForm()
    return render_template(
        "access_grant_funding/view_locked_report.html",
        grant_recipient=grant_recipient,
        submission=submission,
        form=form,
    )
