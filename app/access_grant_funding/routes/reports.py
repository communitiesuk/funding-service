import io
import os
from uuid import UUID

from flask import current_app, flash, redirect, render_template, send_file, url_for
from flask.typing import ResponseReturnValue
from playwright.sync_api import sync_playwright

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
@auto_commit_after_request
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

    if form.validate_on_submit():
        user = get_current_user()

        # Our current flow doesn't have an interstitial step between certifying and submitting a report, but these
        # actions are still self-contained and separate so that if this flow changes in the future we already have it
        # modelled.
        submission.certify(user=user)
        submission.submit(user=user)

        users_needing_confirmation = {submission.certified_by, submission.sent_for_certification_by}
        for unique_user in users_needing_confirmation:
            if unique_user is not None:
                notification_service.send_access_submission_certified_and_submitted(
                    email_address=unique_user.email,
                    submission_helper=submission,
                )

        return redirect(
            url_for(
                "access_grant_funding.confirm_certification",
                organisation_id=organisation_id,
                grant_id=grant_id,
                submission_id=submission.id,
            )
        )

    return render_template(
        "access_grant_funding/view_locked_report.html",
        grant_recipient=grant_recipient,
        submission=submission,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(collection=submission.collection, submission_helper=submission),
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/export-pdf",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def export_report_pdf(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)

    submission = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)

    html_content = render_template(
        "access_grant_funding/view_locked_report_print_baseline.html",
        grant_recipient=grant_recipient,
        submission=submission,
        interpolate=SubmissionHelper.get_interpolator(collection=submission.collection, submission_helper=submission),
    )

    # as we're calling to an external binary this makes sure we're set up if the flask app
    # has defined its own path, this could also be set in the container terraform
    if current_app.config["PLAYWRIGHT_BROWSERS_PATH"] is not None:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = current_app.config["PLAYWRIGHT_BROWSERS_PATH"]

    # note that we're opening a new browser per request
    # with a single request at a time this responds in ~200ms but if we ever anticipate higher
    # simultaneous usage we'd probably want a singleton module to manage the browser connection
    # and close and open pages as needed, this would allow a lot more simultaneous requests to be
    # processed performantly
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            java_script_enabled=False,
            bypass_csp=True,
            http_credentials={
                "username": current_app.config["BASIC_AUTH_USERNAME"],
                "password": current_app.config["BASIC_AUTH_PASSWORD"],
            }
            if current_app.config["BASIC_AUTH_ENABLED"]
            else None,
        )
        page.set_content(html_content, wait_until="load")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            scale=0.9,
            margin={"top": "5mm", "bottom": "5mm", "left": "5mm", "right": "5mm"},
        )
        browser.close()

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{submission.collection.grant.name} - {submission.collection.name}.pdf",
        max_age=0,
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


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/certification-confirmation",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.CERTIFIER)
def confirm_certification(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)
    submission = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)

    if not submission.is_submitted:
        # note we're not redirecting to the route to submission as you might have been directed from
        # there, go somewhere we know will load consistently and the user can step back in
        return redirect(
            url_for("access_grant_funding.list_reports", organisation_id=organisation_id, grant_id=grant_id)
        )

    return render_template(
        "access_grant_funding/reports/submission_confirmation.html",
        grant_recipient=grant_recipient,
        submission=submission,
    )
