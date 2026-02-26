from io import BytesIO
from uuid import UUID

from flask import abort, redirect, render_template, request, send_file, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import has_deliver_grant_role
from app.common.collections.runner import DGFFormRunner
from app.common.collections.types import FileUploadAnswer
from app.common.data import interfaces
from app.common.data.types import FormRunnerState, RoleEnum
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request, s3_service


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@has_deliver_grant_role(RoleEnum.MEMBER)
def submission_tasklist(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(submission_id=submission_id, source=FormRunnerState(source) if source else None)

    if runner.tasklist_form.validate_on_submit():
        if runner.complete_submission(interfaces.user.get_current_user()):
            if runner.submission.is_preview:
                return redirect(
                    url_for(
                        "deliver_grant_funding.return_from_test_submission",
                        collection_id=runner.submission.collection.id,
                        finished=1,
                    )
                )

            return redirect(
                url_for(
                    "deliver_grant_funding.list_report_sections",
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
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/<uuid:question_id>/<any('clear'):action>",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/<uuid:question_id>/<int:add_another_index>",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/<uuid:question_id>/<int:add_another_index>/<any('remove', 'clear'):action>",  # noqa: E501
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_deliver_grant_role(RoleEnum.MEMBER)
def ask_a_question(
    grant_id: UUID,
    submission_id: UUID,
    question_id: UUID,
    add_another_index: int | None = None,
    action: str | None = None,
) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(
        submission_id=submission_id,
        question_id=question_id,
        source=FormRunnerState(source) if source else None,
        add_another_index=add_another_index,
        is_removing=action == "remove",
        is_clearing=action == "clear",
    )

    if not runner.validate_can_show_question_page():
        return redirect(runner.next_url)

    if (
        runner.question_with_add_another_summary_form
        and runner.question_with_add_another_summary_form.validate_on_submit()
    ):
        # todo: review the logic here, almost everything here feels like it should be encapsulated
        #       in the runner with increasing workarounds here
        success = True
        if runner.is_removing:
            success = runner.save_add_another()
        elif not runner.add_another_summary_context:
            # todo: save question answer could aways no-op if theres nothing to save which would make this code
            #       more straight forward
            success = runner.save_question_answer(interfaces.user.get_current_user())

        if success:
            return redirect(runner.next_url)

    is_first_question_in_section_preview = False
    if session.get("test_submission_form_id", None):
        question = runner.questions[0]
        is_first_question_in_section_preview = question == question.form.cached_questions[0]

    return render_template(
        "deliver_grant_funding/runner/ask_a_question.html",
        runner=runner,
        is_first_question_in_section_preview=is_first_question_in_section_preview,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/check-yours-answers/<uuid:form_id>",
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_deliver_grant_role(RoleEnum.MEMBER)
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


# todo: decide if this should be a K:V lookup for a simplified file key or if it should lookup the
# question like other pages
@deliver_grant_funding_blueprint.route(
    "/download/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/<uuid:question_id>", methods=["GET"]
)
@deliver_grant_funding_blueprint.route(
    "/download/grant/<uuid:grant_id>/submissions/<uuid:submission_id>/<uuid:question_id>/<int:add_another_index>",
    methods=["GET"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def download_file(
    grant_id: UUID,
    submission_id: UUID,
    question_id: UUID,
    add_another_index: int | None = None,
) -> ResponseReturnValue:
    submission = SubmissionHelper.load(submission_id=submission_id)
    data = submission.cached_get_answer_for_question(question_id=question_id, add_another_index=add_another_index)
    if not data or not isinstance(data, FileUploadAnswer) or not data.key:
        abort(404)
    # return redirect(s3_service.generate_and_give_access_to_url(answer=data))
    file_bytes = s3_service.download_file(key=data.key)
    return send_file(BytesIO(file_bytes), download_name=data.filename, as_attachment=True, max_age=0)
