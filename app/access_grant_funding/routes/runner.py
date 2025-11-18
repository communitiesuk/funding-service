from typing import Optional
from uuid import UUID

from flask import abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_access_grant_role, is_access_org_member
from app.common.collections.runner import AGFFormRunner
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection, get_submission_by_grant_recipient_collection
from app.common.data.types import FormRunnerState, RoleEnum, SubmissionModeEnum
from app.extensions import auto_commit_after_request


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/collection/<uuid:collection_id>", methods=["GET"]
)
@auto_commit_after_request
@is_access_org_member
def route_to_submission(organisation_id: UUID, grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)
    submission = get_submission_by_grant_recipient_collection(grant_recipient, collection_id)

    if not submission:
        collection = get_collection(collection_id)
        # todo: depending on what we land on with decorators this might check for data provider role
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


# todo: assumes that the route from the reports list page is able to create the submission if it doesn't exist
#       might just need to add that as it will be a pain to try out locally without
@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
# todo: change to has member role for org + grant
#       has member role -> in the method it can reject for not data provider
#       this might be tweaked if read only form is switched up to use the view all sections with stickies
@is_access_org_member
def tasklist(organisation_id: UUID, grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    runner = AGFFormRunner.load(submission_id=submission_id, source=FormRunnerState(source) if source else None)

    if runner.tasklist_form.validate_on_submit():
        if AuthorisationHelper.is_access_grant_data_provider(
            grant_id=grant_id, organisation_id=organisation_id, user=interfaces.user.get_current_user()
        ):
            if runner.complete_submission(interfaces.user.get_current_user()):
                # todo: sign off confirmation and email
                return redirect(
                    url_for(
                        "access_grant_funding.tasklist",
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
@is_access_org_member
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
