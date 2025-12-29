import io
import os
from uuid import UUID

from flask import current_app, flash, redirect, render_template, send_file, url_for
from flask.typing import ResponseReturnValue
from playwright.sync_api import sync_playwright

from app.access_grant_funding.forms import DeclineSignOffForm
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_access_grant_role
from app.common.data.interfaces.collections import get_all_submissions_with_mode_for_collection
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import CollectionType, RoleEnum, SubmissionStatusEnum
from app.common.exceptions import SubmissionValidationFailed
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.submission_mode import get_submission_mode_for_user
from app.extensions import auto_commit_after_request, notification_service
from app.types import FlashMessageType


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports", methods=["GET"]
)
@has_access_grant_role(RoleEnum.MEMBER)
def list_reports(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)
    user = get_current_user()
    submission_mode = get_submission_mode_for_user(user)

    # TODO refactor when we persist the collection status and/or implement multiple rounds
    submissions = []
    for report in grant_recipient.grant.get_access_reports_for_user(user):
        submissions.extend(
            [
                SubmissionHelper(submission=submission)
                for submission in get_all_submissions_with_mode_for_collection(
                    collection_id=report.id,
                    submission_mode=submission_mode,
                    grant_recipient_ids=[grant_recipient.id],
                )
            ]
        )

    return render_template(
        "access_grant_funding/report_list.html",
        reports=grant_recipient.grant.get_access_reports_for_user(user),
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

    if form.validate_on_submit():
        return redirect(
            url_for(
                "access_grant_funding.confirm_report_submission_certify",
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

        # There are two distinct emails for data providers and certifiers in this flow so we want users to receive the
        # relevant ones, even if they have both permissions.
        for data_provider in grant_recipient.data_providers:
            notification_service.send_access_submitter_submission_declined(
                user=data_provider, submission_helper=submission_helper
            )

        for certifier in grant_recipient.certifiers:
            notification_service.send_access_certifier_confirm_submission_declined(
                user=certifier,
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
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/confirm-report-submission-certify",
    methods=["GET", "POST"],
)
@has_access_grant_role(RoleEnum.CERTIFIER)
@auto_commit_after_request
def confirm_report_submission_certify(
    organisation_id: UUID, grant_id: UUID, submission_id: UUID
) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)
    submission_helper = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)
    user = get_current_user()

    if not submission_helper.is_awaiting_sign_off:
        current_app.logger.warning(
            "Confirm certify and submit loaded incorrectly by %(user_id)s for submission %(submission_id)s",
            {"user_id": user.id, "submission_id": submission_id},
        )
        return redirect(
            url_for("access_grant_funding.list_reports", organisation_id=organisation_id, grant_id=grant_id)
        )

    form = GenericSubmitForm()

    if form.validate_on_submit():
        try:
            if submission_helper.collection.requires_certification:
                submission_helper.certify(user)
            submission_helper.submit(user)

            return redirect(
                url_for(
                    "access_grant_funding.submitted_confirmation",
                    organisation_id=organisation_id,
                    grant_id=grant_id,
                    submission_id=submission_id,
                )
            )
        except SubmissionValidationFailed as e:
            flash(e.error_message, FlashMessageType.SUBMISSION_VALIDATION_ERROR)
            return redirect(
                url_for(
                    "access_grant_funding.route_to_submission",
                    organisation_id=organisation_id,
                    grant_id=grant_id,
                    collection_id=submission_helper.collection_id,
                )
            )

    return render_template(
        "access_grant_funding/reports/submit_report.html",
        grant_recipient=grant_recipient,
        submission_helper=submission_helper,
        form=form,
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/confirm-report-submission",
    methods=["GET", "POST"],
)
@has_access_grant_role(RoleEnum.DATA_PROVIDER)
@auto_commit_after_request
def confirm_report_submission(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)
    submission_helper = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)
    user = get_current_user()

    if not submission_helper.status == SubmissionStatusEnum.READY_TO_SUBMIT:
        current_app.logger.warning(
            "Confirm submit loaded incorrectly by %(user_id)s for submission %(submission_id)s",
            {"user_id": user.id, "submission_id": submission_id},
        )
        return redirect(
            url_for("access_grant_funding.list_reports", organisation_id=organisation_id, grant_id=grant_id)
        )

    form = GenericSubmitForm()

    if form.validate_on_submit():
        try:
            submission_helper.submit(user)

            return redirect(
                url_for(
                    "access_grant_funding.submitted_confirmation",
                    organisation_id=organisation_id,
                    grant_id=grant_id,
                    submission_id=submission_id,
                )
            )
        except SubmissionValidationFailed as e:
            flash(e.error_message, FlashMessageType.SUBMISSION_VALIDATION_ERROR)
            return redirect(
                url_for(
                    "access_grant_funding.route_to_submission",
                    organisation_id=organisation_id,
                    grant_id=grant_id,
                    collection_id=submission_helper.collection_id,
                )
            )

    return render_template(
        "access_grant_funding/reports/submit_report.html",
        grant_recipient=grant_recipient,
        submission_helper=submission_helper,
        form=form,
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/submitted-confirmation",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def submitted_confirmation(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = get_grant_recipient(grant_id, organisation_id)
    submission_helper = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)
    user = get_current_user()

    if (
        not submission_helper.is_submitted
        or (
            submission_helper.collection.requires_certification
            and not AuthorisationHelper.is_access_grant_certifier(grant_id, organisation_id, user)
        )
        or (
            not submission_helper.collection.requires_certification
            and not AuthorisationHelper.is_access_grant_data_provider(grant_id, organisation_id, user)
        )
    ):
        # note we're not redirecting to the route to submission as you might have been directed from
        # there, go somewhere we know will load consistently and the user can step back in
        return redirect(
            url_for("access_grant_funding.list_reports", organisation_id=organisation_id, grant_id=grant_id)
        )

    return render_template(
        "access_grant_funding/reports/submitted_confirmation.html",
        grant_recipient=grant_recipient,
        submission_helper=submission_helper,
    )
