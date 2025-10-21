import uuid

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import access_grant_funding_login_required, is_platform_admin
from app.common.collections.runner import AGFFormRunner
from app.common.data import interfaces
from app.common.data.interfaces.collections import create_submission, get_collection
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.temporary import get_submission_by_collection_and_user
from app.common.data.types import FormRunnerState, SubmissionModeEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.extensions import auto_commit_after_request, notification_service

developers_access_blueprint = Blueprint("access", __name__, url_prefix="/access")


@developers_access_blueprint.get("/grants")
@is_platform_admin
def grants_list() -> ResponseReturnValue:
    grants = interfaces.grants.get_all_grants_by_user(interfaces.user.get_current_user())
    return render_template("developers/access/grants_list.html", grants=grants)


# note: no auth decorator on this page, fully public, the template itself deals with varying the response based on
#       anonymous vs logged-in user.
@developers_access_blueprint.route("/grants/<uuid:grant_id>", methods=["GET", "POST"])
def grant_details(grant_id: uuid.UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id)
    current_user = interfaces.user.get_current_user()

    form = GenericSubmitForm()
    if form.validate_on_submit():
        session["next"] = request.full_path
        return redirect(url_for("auth.request_a_link_to_sign_in"))

    submission_helpers = {}
    if current_user.is_authenticated:
        submission_helpers = {
            collection.id: SubmissionHelper.load(submission.id)
            for collection in grant.collections
            if (submission := get_submission_by_collection_and_user(collection, interfaces.user.get_current_user()))
        }

    return render_template(
        "developers/access/grant_details.html",
        grant=grant,
        submission_helpers=submission_helpers,
        form=form,
    )


# todo: this a developers solution only - anything actually doing this should be through POST
#       with sensible permission and integrity checks
@developers_access_blueprint.get("/submissions/start/<uuid:collection_id>")
@auto_commit_after_request
@access_grant_funding_login_required
def start_submission_redirect(collection_id: uuid.UUID) -> ResponseReturnValue:
    current_user = interfaces.user.get_current_user()
    collection = get_collection(collection_id)
    submission = create_submission(collection=collection, created_by=current_user, mode=SubmissionModeEnum.TEST)
    return redirect(url_for("developers.access.submission_tasklist", submission_id=submission.id))


@developers_access_blueprint.route("/submissions/<uuid:submission_id>", methods=["GET", "POST"])
@auto_commit_after_request
@access_grant_funding_login_required
def submission_tasklist(submission_id: uuid.UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = AGFFormRunner.load(submission_id=submission_id, source=FormRunnerState(source) if source else None)

    if runner.tasklist_form.validate_on_submit():
        if runner.complete_submission(interfaces.user.get_current_user()):
            notification_service.send_collection_submission(runner.submission.submission)
            return redirect(url_for("developers.access.collection_confirmation", submission_id=runner.submission.id))

    return render_template(
        "developers/access/collection_tasklist.html",
        runner=runner,
    )


@developers_access_blueprint.route("/submissions/<uuid:submission_id>/<uuid:question_id>", methods=["GET", "POST"])
@access_grant_funding_login_required
@auto_commit_after_request
def ask_a_question(submission_id: uuid.UUID, question_id: uuid.UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = AGFFormRunner.load(
        submission_id=submission_id, question_id=question_id, source=FormRunnerState(source) if source else None
    )

    if not runner.validate_can_show_question_page():
        return redirect(runner.next_url)

    if (
        runner.question_with_add_another_summary_form
        and runner.question_with_add_another_summary_form.validate_on_submit()
    ):
        if not runner.add_another_summary_context:
            runner.save_question_answer()
        return redirect(runner.next_url)

    return render_template(
        "developers/access/ask_a_question.html",
        runner=runner,
        interpolate=SubmissionHelper.get_interpolator(
            runner.submission.collection, submission_helper=runner.submission
        ),
    )


@developers_access_blueprint.route(
    "/submissions/<uuid:submission_id>/check-yours-answers/<uuid:form_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@access_grant_funding_login_required
def check_your_answers(submission_id: uuid.UUID, form_id: uuid.UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = AGFFormRunner.load(
        submission_id=submission_id, form_id=form_id, source=FormRunnerState(source) if source else None
    )

    if runner.check_your_answers_form.validate_on_submit():
        if runner.save_is_form_completed(interfaces.user.get_current_user()):
            return redirect(runner.next_url)

    return render_template("developers/access/check_your_answers.html", runner=runner)


@developers_access_blueprint.route("/submissions/<uuid:submission_id>/confirmation", methods=["GET", "POST"])
@access_grant_funding_login_required
def collection_confirmation(submission_id: uuid.UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)

    if not submission_helper.is_completed:
        current_app.logger.warning(
            "Cannot access submission confirmation for non complete collection for submission_id=%(submission_id)s",
            dict(submission_id=str(submission_helper.id)),
        )
        return redirect(url_for("developers.access.submission_tasklist", submission_id=submission_helper.id))

    return render_template(
        "developers/access/collection_submit_confirmation.html",
        submission_helper=submission_helper,
    )
