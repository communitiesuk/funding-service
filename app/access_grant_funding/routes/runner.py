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
from app.extensions import auto_commit_after_request


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
        # Use the grant recipient's mode to determine the submission mode
        submission_mode = SubmissionModeEnum(grant_recipient.mode.value)
        submission = interfaces.collections.create_submission(
            collection=collection, grant_recipient=grant_recipient, created_by=user, mode=submission_mode
        )

    submission_helper = SubmissionHelper(submission)
    if submission_helper.is_locked_state:
        return redirect(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=organisation_id,
                grant_id=grant_id,
                submission_id=submission.id,
            )
        )
    else:
        return redirect(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=organisation_id,
                grant_id=grant_id,
                submission_id=submission.id,
            )
        )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/tasklist",
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.MEMBER)
def tasklist(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    runner = AGFFormRunner.load(
        submission_id=submission_id,
        source=FormRunnerState(source) if source else None,
        grant_recipient_id=grant_recipient.id,
    )

    if runner.submission.is_locked_state:
        return redirect(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=organisation_id,
                grant_id=grant_id,
                submission_id=submission_id,
            )
        )

    if runner.tasklist_form.validate_on_submit():
        if not AuthorisationHelper.is_access_grant_data_provider(
            grant_id=grant_id, organisation_id=organisation_id, user=interfaces.user.get_current_user()
        ):
            return abort(403, description="Access denied")

        if runner.complete_submission(interfaces.user.get_current_user()):
            if runner.submission.is_submitted:
                return redirect(
                    url_for(
                        "access_grant_funding.confirm_report_submitted",
                        organisation_id=organisation_id,
                        grant_id=grant_id,
                        submission_id=submission_id,
                    )
                )
            elif runner.submission.is_awaiting_sign_off:
                return redirect(
                    url_for(
                        "access_grant_funding.confirm_sent_for_certification",
                        organisation_id=organisation_id,
                        grant_id=grant_id,
                        submission_id=submission_id,
                    )
                )

    # if complete_submission failed, the runner has appended errors to the form which will show to the user
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
        grant_recipient_id=grant_recipient.id,
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
        grant_recipient_id=grant_recipient.id,
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
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/sent_for_sign_off_confirmation",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def confirm_sent_for_certification(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)
    submission_helper = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)
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
        "access_grant_funding/reports/sent_for_sign_off_confirmation.html",
        grant_recipient=grant_recipient,
        submission_helper=submission_helper,
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/submitted_confirmation",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def confirm_report_submitted(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)
    submission_helper = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)
    if not submission_helper.is_submitted:
        return redirect(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=organisation_id,
                grant_id=grant_id,
                submission_id=submission_id,
            )
        )
    return render_template(
        "access_grant_funding/reports/submit_confirmation.html",
        grant_recipient=grant_recipient,
        submission_helper=submission_helper,
    )
