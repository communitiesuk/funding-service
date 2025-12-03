from uuid import UUID

from flask import flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.forms import DeclineSignOffForm
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import has_access_grant_role
from app.common.data.interfaces.collections import get_all_submissions_with_mode_for_collection_with_full_schema
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import CollectionType, RoleEnum, SubmissionModeEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.extensions import auto_commit_after_request, notification_service
from app.types import FlashMessageType


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


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/decline",
    methods=["GET", "POST"],
)
@has_access_grant_role(RoleEnum.CERTIFIER)
@auto_commit_after_request
def decline_report(
    organisation_id: UUID,
    grant_id: UUID,
    submission_id: UUID,
) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)

    submission_helper = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)

    if not (
        submission_helper.is_awaiting_sign_off and submission_helper.collection.type == CollectionType.MONITORING_REPORT
    ):
        return redirect(
            url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=organisation_id,
                grant_id=grant_id,
                collection_id=submission_helper.collection_id,
            )
        )

    form = DeclineSignOffForm()
    if form.validate_on_submit():
        declined_reason = form.decline_reason.data or ""
        certifier_user = get_current_user()
        submission_helper.decline_certification(certifier_user, declined_reason=declined_reason)

        notification_service.send_access_submitter_submission_declined(
            certifier_user=certifier_user, submission_helper=submission_helper
        )
        notification_service.send_access_certifier_confirm_submission_declined(
            certifier_user=certifier_user,
            submission_helper=submission_helper,
        )
        flash(
            {  # type:ignore [arg-type]
                "collection_name": submission_helper.collection.name,
                "grant_name": submission_helper.grant.name,
                "sent_for_certification_by": submission_helper.sent_for_certification_by.name
                if submission_helper.sent_for_certification_by
                else "the submitter",
                "collection_id": submission_helper.collection.id,
            },
            FlashMessageType.SUBMISSION_SIGN_OFF_DECLINED,
        )
        return redirect(
            url_for("access_grant_funding.list_reports", organisation_id=organisation_id, grant_id=grant_id)
        )

    return render_template(
        "access_grant_funding/decline_report.html",
        submission=submission_helper,
        grant_recipient=grant_recipient,
        form=form,
    )
