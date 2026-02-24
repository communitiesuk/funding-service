from functools import partial
from io import BytesIO
from uuid import UUID

from flask import abort, redirect, render_template, request, send_file, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_access_grant_role
from app.common.collections.forms import build_question_form
from app.common.collections.runner import AGFFormRunner
from app.common.collections.types import FileUploadAnswer
from app.common.data import interfaces
from app.common.data.interfaces import rollback
from app.common.data.interfaces.collections import get_collection, get_submissions_by_grant_recipient_collection
from app.common.data.types import FormRunnerState, RoleEnum, SubmissionModeEnum
from app.common.exceptions import SubmissionAnswerConflict
from app.common.expressions import ExpressionContext, interpolate
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.submission_mode import get_submission_mode_for_user
from app.extensions import auto_commit_after_request, s3_service


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/collection/<uuid:collection_id>", methods=["GET"]
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.MEMBER)
def route_to_submission(organisation_id: UUID, grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    collection = get_collection(collection_id, grant_id=grant_id)
    if collection.allow_multiple_submissions:
        return redirect(
            url_for(
                "access_grant_funding.list_collection_submissions",
                organisation_id=organisation_id,
                grant_id=grant_id,
                collection_id=collection_id,
            )
        )

    submissions = get_submissions_by_grant_recipient_collection(grant_recipient, collection_id)
    if len(submissions) > 1:
        raise RuntimeError(
            f"Multiple submissions found for collection {collection_id} and grant recipient {grant_recipient.id}"
        )

    submission = submissions[0] if submissions else None
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
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/collection/<uuid:collection_id>/start",
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.DATA_PROVIDER)
def start_new_multiple_submission(organisation_id: UUID, grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    collection = get_collection(collection_id, grant_id=grant_id, with_full_schema=True)
    question = collection.submission_name_question
    if not collection.allow_multiple_submissions:
        raise abort(404)
    elif question is None:
        raise RuntimeError(f"Collection {collection_id} does not have a submission name question")

    evaluation_context = ExpressionContext.build_expression_context(collection=collection, mode="evaluation")
    interpolation_context = ExpressionContext.build_expression_context(collection=collection, mode="interpolation")

    # NOTE: We somewhat hard-code a requirement here that the question selected can stand alone in its own right.
    #       If we update this in the future to be able to point to eg arbitrary data uploads, we'll need to handle
    #       this and process that automatically rather than show an interstitial question page.
    form_cls = build_question_form([question], evaluation_context, interpolation_context)
    form = form_cls()

    if form.validate_on_submit():
        submission_mode = get_submission_mode_for_user(user, user_organisation=grant_recipient.organisation)
        submission = interfaces.collections.create_submission(
            collection=collection, grant_recipient=grant_recipient, created_by=user, mode=submission_mode
        )
        submission_helper = SubmissionHelper(submission)

        try:
            submission_helper.submit_answer_for_question(question.id, form, user)
        except SubmissionAnswerConflict as e:
            rollback()  # TODO: ideally handle this more gracefully, but for now reusing the logic in
            # `submit_answer_for_question` feels more reliable
            form.attach_error_for_question(question, e.message)
        else:
            return redirect(
                url_for(
                    "access_grant_funding.tasklist",
                    organisation_id=organisation_id,
                    grant_id=grant_id,
                    submission_id=submission.id,
                )
            )

    return render_template(
        "access_grant_funding/start_new_multiple_submission.html",
        collection=collection,
        question=question,
        form=form,
        grant_recipient=grant_recipient,
        interpolator=partial(interpolate, context=interpolation_context),
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

        if runner.validate_submission():
            if runner.submission.collection.requires_certification:
                runner.submission.mark_as_sent_for_certification(interfaces.user.get_current_user())
                return redirect(
                    url_for(
                        "access_grant_funding.confirm_sent_for_certification",
                        organisation_id=organisation_id,
                        grant_id=grant_id,
                        submission_id=submission_id,
                    )
                )
            return redirect(
                url_for(
                    "access_grant_funding.confirm_report_submission_direct_submission",
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
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>/<any('clear'):action>",
    methods=["GET", "POST"],
)
@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>/<int:add_another_index>",
    methods=["GET", "POST"],
)
@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>/<int:add_another_index>/<any('remove', 'clear'):action>",  # noqa: E501
    methods=["GET", "POST"],
)
@auto_commit_after_request
@has_access_grant_role(RoleEnum.DATA_PROVIDER)
def ask_a_question(
    organisation_id: UUID,
    grant_id: UUID,
    submission_id: UUID,
    question_id: UUID,
    add_another_index: int | None = None,
    action: str | None = None,
) -> ResponseReturnValue:
    source = request.args.get("source")
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)

    runner = AGFFormRunner.load(
        submission_id=submission_id,
        question_id=question_id,
        source=FormRunnerState(source) if source else None,
        add_another_index=add_another_index,
        grant_recipient_id=grant_recipient.id,
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
            # todo: always call save, it should check this itself and no-op
            success = runner.save_question_answer(interfaces.user.get_current_user())

        if success:
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
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/sent-for-sign-off-confirmation",
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


# todo: decide if this should be a K:V lookup for a simplified file key or if it should lookup the
# question like other pages
@access_grant_funding_blueprint.route(
    "/download/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>",
    methods=["GET"],
)
@access_grant_funding_blueprint.route(
    "/download/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/reports/<uuid:submission_id>/questions/<uuid:question_id>/<int:add_another_index>",
    methods=["GET"],
)
@has_access_grant_role(RoleEnum.MEMBER)
def download_file(
    organisation_id: UUID,
    grant_id: UUID,
    submission_id: UUID,
    question_id: UUID,
    add_another_index: int | None = None,
) -> ResponseReturnValue:
    grant_recipient = interfaces.grant_recipients.get_grant_recipient(grant_id, organisation_id)
    submission = SubmissionHelper.load(submission_id=submission_id, grant_recipient_id=grant_recipient.id)
    data = submission.cached_get_answer_for_question(question_id=question_id, add_another_index=add_another_index)
    if not data or not isinstance(data, FileUploadAnswer) or not data.key:
        abort(404)
    # return redirect(s3_service.generate_and_give_access_to_url(answer=data))
    file_bytes = s3_service.download_file(key=data.key)
    return send_file(BytesIO(file_bytes), download_name=data.filename, as_attachment=True)
