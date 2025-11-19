from typing import Optional
from uuid import UUID

from flask import abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_access_grant_role
from app.common.collections.runner import AGFFormRunner
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection, get_submission_by_grant_recipient_collection
from app.common.data.types import FormRunnerState, RoleEnum, SubmissionModeEnum
from app.common.helpers.collections import SubmissionHelper
from app.extensions import auto_commit_after_request, notification_service


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/collection/<uuid:collection_id>", methods=["GET"]
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.MEMBER)
def route_to_submission(organisation_id: UUID, grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)
    submission = get_submission_by_grant_recipient_collection(grant_recipient, collection_id)

    if not submission:
        # ensure the collection is part of this grant
        collection = get_collection(collection_id, grant_id=grant_id)
        submission = interfaces.collections.create_submission(
            collection=collection, grant_recipient=grant_recipient, created_by=user, mode=SubmissionModeEnum.LIVE
        )
    return redirect(
        url_for(
            "access_grant_funding.tasklist",
            organisation_id=organisation_id,
            grant_id=grant_id,
            submission_id=submission.id,
        )
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.MEMBER)
def tasklist(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    runner = AGFFormRunner.load(submission_id=submission_id, source=FormRunnerState(source) if source else None)

    if runner.tasklist_form.validate_on_submit():
        if AuthorisationHelper.is_access_grant_data_provider(
            grant_id=grant_id, organisation_id=organisation_id, user=interfaces.user.get_current_user()
        ):
            if runner.complete_submission(interfaces.user.get_current_user(), requires_certification=True):
                for data_provider in grant_recipient.data_providers:
                    notification_service.send_access_submission_signed_off_confirmation(
                        data_provider.email, submission=runner.submission.submission
                    )
                for certifier in grant_recipient.certifiers:
                    notification_service.send_access_submission_ready_to_certify(
                        certifier.email,
                        submission=runner.submission.submission,
                        submitted_by=interfaces.user.get_current_user(),
                    )

                return redirect(
                    url_for(
                        "access_grant_funding.confirm_sent_for_certification",
                        organisation_id=organisation_id,
                        grant_id=grant_id,
                        submission_id=submission_id,
                    )
                )
        else:
            return abort(403, description="Access denied")

    return render_template("access_grant_funding/reports/tasklist.html", grant_recipient=grant_recipient, runner=runner)


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>",
    methods=["GET", "POST"],
)
@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>/<int:add_another_index>",
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.DATA_PROVIDER)
def ask_a_question(
    organisation_id: UUID,
    grant_id: UUID,
    submission_id: UUID,
    question_id: UUID,
    add_another_index: Optional[int] = None,
) -> ResponseReturnValue:
    source = request.args.get("source")
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    runner = AGFFormRunner.load(
        submission_id=submission_id,
        question_id=question_id,
        source=FormRunnerState(source) if source else None,
        add_another_index=add_another_index,
    )

    if not runner.validate_can_show_question_page():
        return redirect(runner.next_url)

    if (
        runner.question_with_add_another_summary_form
        and runner.question_with_add_another_summary_form.validate_on_submit()
    ):
        # todo: always call save, it should check this itself and no-op
        if not runner.add_another_summary_context:
            runner.save_question_answer()
        return redirect(runner.next_url)

    return render_template(
        "access_grant_funding/reports/ask_a_question.html", grant_recipient=grant_recipient, runner=runner
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/check-your-answers/<uuid:section_id>",
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.MEMBER)
def check_your_answers(
    organisation_id: UUID, grant_id: UUID, submission_id: UUID, section_id: UUID
) -> ResponseReturnValue:
    source = request.args.get("source")
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    runner = AGFFormRunner.load(
        submission_id=submission_id,
        form_id=section_id,
        source=FormRunnerState(source) if source else None,
    )

    if runner.check_your_answers_form.validate_on_submit():
        if AuthorisationHelper.is_access_grant_data_provider(
            grant_id=grant_id, organisation_id=organisation_id, user=interfaces.user.get_current_user()
        ):
            if runner.save_is_form_completed(interfaces.user.get_current_user()):
                return redirect(runner.next_url)
        else:
            return abort(403, description="Access denied")

    return render_template(
        "access_grant_funding/reports/check_your_answers.html", grant_recipient=grant_recipient, runner=runner
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/confirmation",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def confirm_sent_for_certification(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)
    submission_helper = SubmissionHelper.load(submission_id=submission_id)
    if not submission_helper.is_locked_state:
        return redirect(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=organisation_id,
                grant_id=grant_id,
                submission_id=submission_id,
            )
        )
    return render_template(
        "access_grant_funding/reports/confirmation.html",
        grant_recipient=grant_recipient,
        submission_helper=submission_helper,
    )
