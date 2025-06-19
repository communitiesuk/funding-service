from enum import StrEnum
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from flask import abort, current_app, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from wtforms import Field

from app.common.auth.decorators import platform_admin_role_required
from app.common.collections.forms import build_question_form
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_collection,
    create_form,
    create_question,
    create_section,
    create_submission,
    get_collection,
    get_form_by_id,
    get_question_by_id,
    get_section_by_id,
    move_form_down,
    move_form_up,
    move_question_down,
    move_question_up,
    move_section_down,
    move_section_up,
    update_collection,
    update_form,
    update_question,
    update_section,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.temporary import (
    delete_collection,
    delete_form,
    delete_question,
    delete_section,
    delete_submissions_created_by_user,
)
from app.common.data.types import QuestionDataType, SubmissionModeEnum, SubmissionStatusEnum
from app.common.expressions.helpers import (
    get_managed_condition_form,
    get_managed_validation_form,
    get_supported_form_questions,
    parse_condition_form,
)
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.forms import (
    CollectionForm,
    FormForm,
    QuestionForm,
    QuestionTypeForm,
    SectionForm,
)
from app.developers import developers_blueprint
from app.developers.forms import (
    CheckYourAnswersForm,
    ConditionSelectQuestionForm,
    ConfirmDeletionForm,
    PreviewCollectionForm,
    SubmitSubmissionForm,
)
from app.extensions import auto_commit_after_request, notification_service

if TYPE_CHECKING:
    from app.common.data.models import Form, Question, Submission


@developers_blueprint.context_processor
def inject_variables() -> dict[str, Any]:
    return dict(show_watermark=True)


@developers_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
@platform_admin_role_required
def grant_developers(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("developers/grant_developers.html", grant=grant)


@developers_blueprint.route("/grants/<uuid:grant_id>/collections", methods=["GET"])
@platform_admin_role_required
def grant_developers_collections(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("developers/list_collections.html", grant=grant)


@developers_blueprint.route("/grants/<uuid:grant_id>/collections/set-up", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def setup_collection(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = CollectionForm()
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            user = interfaces.user.get_current_user()
            create_collection(name=form.name.data, user=user, grant=grant)
            return redirect(url_for("developers.grant_developers_collections", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("developers/add_collection.html", grant=grant, form=form)


@developers_blueprint.route("/grants/<uuid:grant_id>/collections/<uuid:collection_id>", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def manage_collection(grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id)  # TODO: handle collection versioning; this just grabs latest.

    form = PreviewCollectionForm()
    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_collection(collection_id=collection.id)
        # TODO: Flash message for deletion?
        return redirect(url_for("developers.grant_developers_collections", grant_id=grant_id))

    if form.validate_on_submit() and form.submit.data:
        user = interfaces.user.get_current_user()
        delete_submissions_created_by_user(grant_id=collection.grant_id, created_by_id=user.id)
        submission = create_submission(collection=collection, created_by=user, mode=SubmissionModeEnum.TEST)
        return redirect(url_for("developers.submission_tasklist", submission_id=submission.id))

    return render_template(
        "developers/manage_collection.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


@developers_blueprint.route("/grants/<uuid:grant_id>/collections/<uuid:collection_id>/edit", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def edit_collection(grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id)  # TODO: handle collection versioning; this just grabs latest.
    form = CollectionForm(obj=collection)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            update_collection(name=form.name.data, collection=collection)
            return redirect(url_for("developers.manage_collection", grant_id=grant_id, collection_id=collection_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_collection.html",
        grant=collection.grant,
        collection=collection,
        form=form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/add", methods=["GET", "POST"]
)
@platform_admin_role_required
@auto_commit_after_request
def add_section(grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id)  # TODO: handle collection versioning; this just grabs latest.
    form = SectionForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_section(
                title=form.title.data,
                collection=collection,
            )
            return redirect(url_for("developers.list_sections", grant_id=grant_id, collection_id=collection_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("developers/add_section.html", grant=collection.grant, collection=collection, form=form)


@developers_blueprint.route("/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/", methods=["GET"])
@platform_admin_role_required
def list_sections(
    grant_id: UUID,
    collection_id: UUID,
) -> ResponseReturnValue:
    collection = get_collection(collection_id)
    return render_template(
        "developers/list_sections.html",
        grant=collection.grant,
        collection=collection,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/move/<string:direction>",
    methods=["POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def move_section(grant_id: UUID, collection_id: UUID, section_id: UUID, direction: str) -> ResponseReturnValue:
    section = get_section_by_id(section_id)

    if direction == "up":
        move_section_up(section)
    elif direction == "down":
        move_section_down(section)
    else:
        abort(400)

    return redirect(url_for("developers.list_sections", grant_id=grant_id, collection_id=collection_id))


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/manage",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def manage_section(
    grant_id: UUID,
    collection_id: UUID,
    section_id: UUID,
) -> ResponseReturnValue:
    section = get_section_by_id(section_id)

    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_section(section_id=section_id)
        # TODO: Flash message for deletion?
        return redirect(url_for("developers.manage_collection", grant_id=grant_id, collection_id=collection_id))

    return render_template(
        "developers/manage_section.html",
        grant=section.collection.grant,
        collection=section.collection,
        section=section,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/move/<string:direction>",
    methods=["POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def move_form(
    grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID, direction: str
) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    if direction == "up":
        move_form_up(form)
    elif direction == "down":
        move_form_down(form)
    else:
        abort(400)

    return redirect(
        url_for(
            "developers.manage_section",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
        )
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/manage",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def manage_form(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)

    form = ConfirmDeletionForm()
    if "delete" in request.args and form.validate_on_submit() and form.confirm_deletion.data:
        delete_form(form_id=form_id)
        # TODO: Flash message for deletion?
        return redirect(
            url_for("developers.manage_section", grant_id=grant_id, collection_id=collection_id, section_id=section_id)
        )

    return render_template(
        "developers/manage_form.html",
        grant=db_form.section.collection.grant,
        section=db_form.section,
        collection=db_form.section.collection,
        db_form=db_form,
        form=form if "delete" in request.args else None,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/edit",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def edit_section(grant_id: UUID, collection_id: UUID, section_id: UUID) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form = SectionForm(obj=section)
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            update_section(section=section, title=form.title.data)
            return redirect(
                url_for(
                    "developers.manage_section",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_section.html",
        grant=section.collection.grant,
        collection=section.collection,
        section=section,
        form=form,
    )


# TODO: having this method do both selecting the type and adding the form feels like too much
@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/add",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def add_form(grant_id: UUID, collection_id: UUID, section_id: UUID) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form_type = request.args.get("form_type", None)
    if not form_type:
        return render_template(
            "developers/select_form_type.html",
            grant=section.collection.grant,
            collection=section.collection,
            section=section,
        )

    form = FormForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_form(title=form.title.data, section=section)
            return redirect(
                url_for(
                    "developers.manage_section",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template(
        "developers/add_form.html",
        grant=section.collection.grant,
        collection=section.collection,
        section=section,
        form_type=form_type,
        form=form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/edit",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def edit_form(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = FormForm(obj=db_form)
    if wt_form.validate_on_submit():
        try:
            assert wt_form.title.data is not None
            update_form(form=db_form, title=wt_form.title.data)
            return redirect(
                url_for(
                    "developers.manage_form",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_form.html",
        grant=db_form.section.collection.grant,
        collection=db_form.section.collection,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add/choose-type",
    methods=["GET", "POST"],
)
@platform_admin_role_required
def choose_question_type(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))
    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data
        return redirect(
            url_for(
                "developers.add_question",
                grant_id=grant_id,
                collection_id=collection_id,
                section_id=section_id,
                form_id=form_id,
                question_data_type=question_data_type,
            )
        )
    return render_template(
        "developers/choose_question_type.html",
        grant=db_form.section.collection.grant,
        collection=db_form.section.collection,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def add_question(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    question_data_type_arg = request.args.get("question_data_type", QuestionDataType.TEXT_SINGLE_LINE.name)
    question_data_type_enum = QuestionDataType.coerce(question_data_type_arg)

    wt_form = QuestionForm()
    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            create_question(
                form=form,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                data_type=question_data_type_enum,
            )
            return redirect(
                url_for(
                    "developers.manage_form",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/add_question.html",
        grant=form.section.collection.grant,
        collection=form.section.collection,
        section=form.section,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/move/<string:direction>",
    methods=["POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def move_question(
    grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID, question_id: UUID, direction: str
) -> ResponseReturnValue:
    question = get_question_by_id(question_id=question_id)

    if direction == "up":
        move_question_up(question)
    elif direction == "down":
        move_question_down(question)
    else:
        abort(400)

    return redirect(
        url_for(
            "developers.manage_form",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
            form_id=form_id,
        )
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/edit",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def edit_question(
    grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID, question_id: UUID
) -> ResponseReturnValue:
    question = get_question_by_id(question_id=question_id)
    wt_form = QuestionForm(obj=question)

    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_question(question_id=question_id)
        # TODO: Flash message for deletion?
        return redirect(
            url_for(
                "developers.manage_form",
                grant_id=grant_id,
                collection_id=collection_id,
                section_id=section_id,
                form_id=form_id,
            )
        )

    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            update_question(question=question, text=wt_form.text.data, hint=wt_form.hint.data, name=wt_form.name.data)
            return redirect(
                url_for(
                    "developers.manage_form",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_question.html",
        grant=question.form.section.collection.grant,
        collection=question.form.section.collection,
        section=question.form.section,
        db_form=question.form,
        question=question,
        form=wt_form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/add-condition",
    methods=["GET", "POST"],
)
@platform_admin_role_required
def add_question_condition_select_question(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)
    form = ConditionSelectQuestionForm()

    supported_questions = get_supported_form_questions(question)
    form.add_question_options(supported_questions)

    if form.validate_on_submit():
        return redirect(
            url_for(
                "developers.add_question_condition",
                grant_id=grant_id,
                question_id=question_id,
                depends_on_question_id=form.question.data,
            )
        )

    return render_template(
        "developers/add_question_condition_select_question.html",
        question=question,
        supported_questions=supported_questions,
        grant=question.form.section.collection.grant,
        form=form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/add-condition/<uuid:depends_on_question_id>",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def add_question_condition(grant_id: UUID, question_id: UUID, depends_on_question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)
    depends_on_question = get_question_by_id(depends_on_question_id)

    form = get_managed_condition_form(depends_on_question)()

    if form.validate_on_submit():
        expression = parse_condition_form(depends_on_question, form)
        interfaces.collections.add_question_condition(question, interfaces.user.get_current_user(), expression)

        return redirect(
            url_for(
                "developers.edit_question",
                grant_id=grant_id,
                collection_id=question.form.section.collection.id,
                section_id=question.form.section.id,
                form_id=question.form.id,
                question_id=question.id,
            )
        )

    return render_template(
        "developers/add_question_condition_select_condition_type.html",
        question=question,
        depends_on_question=depends_on_question,
        grant=question.form.section.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/add-validation",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def add_question_validation(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)

    ValidationForm = get_managed_validation_form(question)
    form = ValidationForm()

    if form and form.validate_on_submit():
        expression = form.get_expression(question)

        try:
            interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(f"“{expression.description}” validation already exists on the question.")
        else:
            return redirect(
                url_for(
                    "developers.edit_question",
                    grant_id=grant_id,
                    collection_id=question.form.section.collection.id,
                    section_id=question.form.section.id,
                    form_id=question.form.id,
                    question_id=question.id,
                )
            )

    return render_template(
        "developers/add_question_validation.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
    )


class FormRunnerSourceEnum(StrEnum):
    QUESTION = "question"
    TASKLIST = "tasklist"
    CHECK_YOUR_ANSWERS = "check-your-answers"


def _get_form_runner_link_from_source(
    source: str | None,
    submission: Optional["Submission"] = None,
    form: Optional["Form"] = None,
    question: Optional["Question"] = None,
) -> str | None:
    if not source:
        return None

    if source == FormRunnerSourceEnum.QUESTION and submission and question:
        return url_for("developers.ask_a_question", submission_id=submission.id, question_id=question.id)
    elif source == FormRunnerSourceEnum.TASKLIST and submission:
        return url_for("developers.submission_tasklist", submission_id=submission.id)
    elif source == FormRunnerSourceEnum.CHECK_YOUR_ANSWERS and submission and form:
        return url_for("developers.check_your_answers", submission_id=submission.id, form_id=form.id)

    return None


@developers_blueprint.route("/submissions/<uuid:submission_id>", methods=["GET", "POST"])
@auto_commit_after_request
@platform_admin_role_required
def submission_tasklist(submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)
    form = SubmitSubmissionForm()

    if form.validate_on_submit():
        try:
            submission_helper.submit(interfaces.user.get_current_user())
            notification_service.send_collection_submission(submission_helper.submission)
            return redirect(url_for("developers.collection_confirmation", submission_id=submission_helper.id))
        except ValueError:
            form.submit.errors.append("You must complete all forms before submitting the collection")  # type:ignore[attr-defined]

    return render_template(
        "developers/collection_tasklist.html",
        submission_helper=submission_helper,
        statuses=SubmissionStatusEnum,
        back_link_source_enum=FormRunnerSourceEnum,
        form=form,
    )


@developers_blueprint.route("/submissions/<uuid:submission_id>/confirmation", methods=["GET", "POST"])
@platform_admin_role_required
def collection_confirmation(submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)

    if submission_helper.status != SubmissionStatusEnum.COMPLETED:
        current_app.logger.warning(
            "Cannot access submission confirmation for non complete collection for submission_id=%(submission_id)s",
            dict(submission_id=str(submission_helper.id)),
        )
        return redirect(url_for("developers.submission_tasklist", submission_id=submission_helper.id))

    return render_template(
        "developers/collection_submit_confirmation.html",
        submission_helper=submission_helper,
    )


@developers_blueprint.route("/submissions/<uuid:submission_id>/<uuid:question_id>", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def ask_a_question(submission_id: UUID, question_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)
    question = submission_helper.get_question(question_id)
    answer = submission_helper.get_answer_for_question(question.id)

    # this method should work as long as data types are a single field and may
    # need to be revised if we have compound data types
    form = build_question_form(question)(question=answer.root if answer else None)

    if submission_helper.is_completed:
        if form.is_submitted():
            # TODO: Add an error flash message?
            pass
        return redirect(url_for("developers.check_your_answers", submission_id=submission_id, form_id=question.form_id))

    if form.validate_on_submit():
        submission_helper.submit_answer_for_question(question.id, form)

        if request.args.get("source") == FormRunnerSourceEnum.CHECK_YOUR_ANSWERS:
            return redirect(
                url_for("developers.check_your_answers", submission_id=submission_id, form_id=question.form_id)
            )

        next_question = submission_helper.get_next_question(current_question_id=question_id)
        if next_question:
            return redirect(
                url_for("developers.ask_a_question", submission_id=submission_id, question_id=next_question.id)
            )

        return redirect(url_for("developers.check_your_answers", submission_id=submission_id, form_id=question.form_id))

    previous_question = submission_helper.get_previous_question(current_question_id=question_id)
    back_link_from_context = _get_form_runner_link_from_source(
        source=request.args.get("source"),
        submission=submission_helper.submission,
        form=question.form,
        question=question,
    )
    back_link = (
        back_link_from_context
        if back_link_from_context
        else url_for(
            "developers.ask_a_question", submission_id=submission_helper.submission.id, question_id=previous_question.id
        )
        if previous_question
        else url_for("developers.submission_tasklist", submission_id=submission_helper.submission.id)
    )
    return render_template(
        "developers/ask_a_question.html",
        back_link=back_link,
        submission_helper=submission_helper,
        form=form,
        question=question,
        question_types=QuestionDataType,
        back_link_source_enum=FormRunnerSourceEnum,
    )


@developers_blueprint.route(
    "/submissions/<uuid:submission_id>/check-yours-answers/<uuid:form_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@platform_admin_role_required
def check_your_answers(submission_id: UUID, form_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)
    collection_form = submission_helper.get_form(form_id)

    form = CheckYourAnswersForm(
        section_completed=(
            "yes" if submission_helper.get_status_for_form(collection_form) == SubmissionStatusEnum.COMPLETED else None
        )
    )
    previous_question = submission_helper.get_last_question_for_form(collection_form)
    assert previous_question

    back_link_from_context = _get_form_runner_link_from_source(
        source=request.args.get("source"), submission=submission_helper.submission, form=collection_form
    )
    back_link = (
        back_link_from_context
        if back_link_from_context
        else url_for(
            "developers.ask_a_question", submission_id=submission_helper.submission.id, question_id=previous_question.id
        )
    )

    all_questions_answered, _ = submission_helper.get_all_questions_are_answered_for_form(collection_form)
    form.set_is_required(all_questions_answered)

    if form.validate_on_submit():
        try:
            submission_helper.toggle_form_completed(
                form=collection_form,
                user=interfaces.user.get_current_user(),
                is_complete=form.section_completed.data == "yes",
            )
            return redirect(url_for("developers.submission_tasklist", submission_id=submission_helper.id))
        except ValueError:
            form.section_completed.errors.append(  # type:ignore[attr-defined]
                "You must complete all questions before marking this section as complete"
            )

    return render_template(
        "developers/check_your_answers.html",
        back_link=back_link,
        submission_helper=submission_helper,
        collection_form=collection_form,
        form=form,
        back_link_source_enum=FormRunnerSourceEnum,
    )


@developers_blueprint.route(
    "/collections/<uuid:collection_id>/submissions/<submission_mode:submission_mode>",
    methods=["GET"],
)
@platform_admin_role_required
def list_submissions_for_collection(collection_id: UUID, submission_mode: SubmissionModeEnum) -> ResponseReturnValue:
    collection = interfaces.collections.get_collection(collection_id, with_full_schema=True)

    # FIXME: optimise this to only _fetch_ the live or test submissions? The relationship will fetch all submissions
    #        at the moment and filter on the python side.
    _matching_submissions = (
        collection.test_submissions if submission_mode == SubmissionModeEnum.TEST else collection.live_submissions
    )
    submissions = [SubmissionHelper(submission) for submission in _matching_submissions]

    return render_template(
        "developers/list_submissions.html",
        back_link=url_for("developers.manage_collection", collection_id=collection.id, grant_id=collection.grant.id),
        grant=collection.grant,
        collection=collection,
        submissions=submissions,
        is_test_mode=submission_mode == SubmissionModeEnum.TEST,
        statuses=SubmissionStatusEnum,
    )


@developers_blueprint.route("/submission/<uuid:submission_id>", methods=["GET"])
@platform_admin_role_required
def manage_submission(submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)

    return render_template(
        "developers/manage_submission.html",
        back_link=url_for(
            "developers.list_submissions_for_collection",
            collection_id=submission_helper.collection.id,
            submission_mode=submission_helper.submission.mode,
        ),
        submission_helper=submission_helper,
        grant=submission_helper.collection.grant,
        collection=submission_helper.collection,
        statuses=SubmissionStatusEnum,
    )
