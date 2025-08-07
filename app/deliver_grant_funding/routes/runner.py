from uuid import UUID

from flask import redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import has_grant_role
from app.common.collections.runner import DGFFormRunner
from app.common.data import interfaces
from app.common.data.types import FormRunnerState, RoleEnum
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@has_grant_role(RoleEnum.MEMBER)
def submission_tasklist(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(submission_id=submission_id, source=FormRunnerState(source) if source else None)

    if runner.tasklist_form.validate_on_submit():
        if runner.complete_submission(interfaces.user.get_current_user()):
            if runner.submission.is_test:
                return redirect(
                    url_for(
                        "deliver_grant_funding.return_from_test_submission",
                        collection_id=runner.submission.collection.id,
                        finished=1,
                    )
                )

            return redirect(
                url_for(
                    "deliver_grant_funding.list_report_tasks",
                    grant_id=runner.submission.grant.id,
                    report_id=runner.submission.collection.id,
                )
            )

    return render_template(
        "deliver_grant_funding/runner/collection_tasklist.html",
        runner=runner,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/<uuid:question_id>", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def ask_a_question(grant_id: UUID, submission_id: UUID, question_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(
        submission_id=submission_id, question_id=question_id, source=FormRunnerState(source) if source else None
    )

    if not runner.validate_can_show_question_page():
        return redirect(runner.next_url)

    if runner.question_form and runner.question_form.validate_on_submit():
        runner.save_question_answer()
        return redirect(runner.next_url)

    return render_template("deliver_grant_funding/runner/ask_a_question.html", runner=runner)


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/check-yours-answers/<uuid:form_id>",
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_grant_role(RoleEnum.MEMBER)
def check_your_answers(grant_id: UUID, submission_id: UUID, form_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(
        submission_id=submission_id, form_id=form_id, source=FormRunnerState(source) if source else None
    )

    if runner.check_your_answers_form.validate_on_submit():
        if runner.save_is_form_completed(interfaces.user.get_current_user()):
            if form_id == session.get("test_submission_form_id", None):
                return redirect(
                    url_for(
                        "deliver_grant_funding.return_from_test_submission",
                        collection_id=runner.submission.collection.id,
                        finished=1,
                    )
                )

            return redirect(runner.next_url)

    return render_template("deliver_grant_funding/runner/check_your_answers.html", runner=runner)
