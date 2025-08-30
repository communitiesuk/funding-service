import io
import uuid
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from flask import abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask.typing import ResponseReturnValue
from pydantic import BaseModel, ValidationError
from wtforms import Field

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_grant_role
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    DataSourceItemReferenceDependencyException,
    DependencyOrderException,
    create_collection,
    create_form,
    create_group,
    create_question,
    delete_collection,
    delete_form,
    delete_question,
    get_collection,
    get_component_by_id,
    get_expression_by_id,
    get_form_by_id,
    get_group_by_id,
    get_question_by_id,
    move_component_down,
    move_component_up,
    move_form_down,
    move_form_up,
    raise_if_question_has_any_dependencies,
    remove_question_expression,
    update_collection,
    update_form,
    update_group,
    update_question,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import (
    CollectionType,
    ExpressionType,
    GroupDisplayOptions,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.expressions.forms import build_managed_expression_form
from app.common.expressions.registry import get_managed_validators_by_data_type
from app.common.forms import GenericConfirmDeletionForm, GenericSubmitForm
from app.common.helpers.collections import CollectionHelper, SubmissionHelper
from app.deliver_grant_funding.forms import (
    AddGuidanceForm,
    AddTaskForm,
    ConditionSelectQuestionForm,
    GroupDisplayOptionsForm,
    GroupForm,
    QuestionForm,
    QuestionTypeForm,
    SetUpReportForm,
)
from app.deliver_grant_funding.helpers import start_testing_submission
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request
from app.types import FlashMessageType

if TYPE_CHECKING:
    from app.common.data.models import Group, Question


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/reports", methods=["GET", "POST"])
@has_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_reports(grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)

    delete_wtform, delete_report = None, None
    if delete_report_id := request.args.get("delete"):
        if not AuthorisationHelper.has_grant_role(grant_id, RoleEnum.ADMIN, user=get_current_user()):
            return redirect(url_for("deliver_grant_funding.list_reports", grant_id=grant_id))

        delete_report = get_collection(
            uuid.UUID(delete_report_id), grant_id=grant_id, type_=CollectionType.MONITORING_REPORT
        )
        if delete_report.live_submissions:
            abort(403)

        if delete_report and not delete_report.live_submissions:
            delete_wtform = GenericConfirmDeletionForm()

            if delete_wtform and delete_wtform.validate_on_submit():
                delete_collection(delete_report)

                return redirect(url_for("deliver_grant_funding.list_reports", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/reports/list_reports.html",
        grant=grant,
        delete_form=delete_wtform,
        delete_report=delete_report,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/set-up-report", methods=["GET", "POST"])
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def set_up_report(grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id)
    form = SetUpReportForm()
    if form.validate_on_submit():
        assert form.name.data
        try:
            create_collection(
                name=form.name.data,
                user=interfaces.user.get_current_user(),
                grant=grant,
                type_=CollectionType.MONITORING_REPORT,
            )
            # TODO: Redirect to the 'view collection' page when we've added it.
            return redirect(url_for("deliver_grant_funding.list_reports", grant_id=grant_id))

        except DuplicateValueError:
            form.name.errors.append("A report with this name already exists")  # type: ignore[attr-defined]

    return render_template("deliver_grant_funding/reports/set_up_report.html", grant=grant, form=form)


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/report/<uuid:report_id>/change-name", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_report_name(grant_id: UUID, report_id: UUID) -> ResponseReturnValue:
    # NOTE: this fetches the _latest version_ of the collection with this ID
    report = get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

    form = SetUpReportForm(obj=report)
    if form.validate_on_submit():
        assert form.name.data
        try:
            update_collection(report, name=form.name.data)
            return redirect(url_for("deliver_grant_funding.list_reports", grant_id=report.grant_id))
        except DuplicateValueError:
            # FIXME: standardise+consolidate how we handle form errors raised from interfaces
            form.name.errors.append("A report with this name already exists")  # type: ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/reports/change_report_name.html",
        grant=report.grant,
        report=report,
        form=form,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/report/<uuid:report_id>", methods=["GET", "POST"])
@has_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_report_tasks(grant_id: UUID, report_id: UUID) -> ResponseReturnValue:
    report = get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT, with_full_schema=True)
    form = GenericSubmitForm()

    if report.has_non_default_sections:
        raise RuntimeError(f"Report {report_id} has non-default sections - `add_task` needs updating to handle this.")

    if form.validate_on_submit() and form.submit.data:
        return start_testing_submission(collection=report)

    return render_template(
        "deliver_grant_funding/reports/list_report_tasks.html",
        grant=report.grant,
        report=report,
        form=form,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/form/<uuid:form_id>/move-<direction>")
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def move_task(grant_id: UUID, form_id: UUID, direction: str) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    try:
        match direction:
            case "up":
                move_form_up(form)
            case "down":
                move_form_down(form)
            case _:
                return abort(400)
    except DependencyOrderException as e:
        flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type: ignore[arg-type]

    return redirect(
        url_for("deliver_grant_funding.list_report_tasks", grant_id=grant_id, report_id=form.section.collection_id)
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/report/<uuid:report_id>/add-task", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_task(grant_id: UUID, report_id: UUID) -> ResponseReturnValue:
    report = get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

    # Technically this isn't going to be always correct; if users create a report, add a first task, then delete that
    # task, they will be able to add a task from the 'list report tasks' page - but the backlink will take them to the
    # 'list reports' page. This is an edge case I'm not handling right now because: 1) rare, 2) backlinks that are
    # perfect are hard and it doesn't feel worth it yet.
    back_link = (
        url_for("deliver_grant_funding.list_report_tasks", grant_id=grant_id, report_id=report_id)
        if report.forms
        else url_for("deliver_grant_funding.list_reports", grant_id=grant_id)
    )

    if report.has_non_default_sections:
        raise RuntimeError(f"Report {report_id} has non-default sections - `add_task` needs updating to handle this.")

    form = AddTaskForm(obj=report)
    if form.validate_on_submit():
        assert form.title.data
        try:
            create_form(
                title=form.title.data,
                section=report.sections[0],
                collection=report,
            )
            return redirect(url_for("deliver_grant_funding.list_report_tasks", grant_id=grant_id, report_id=report.id))

        except DuplicateValueError:
            form.title.errors.append("A task with this name already exists")  # type: ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/reports/add_task.html", grant=report.grant, report=report, form=form, back_link=back_link
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/change-name", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_form_name(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    # NOTE: this fetches the _latest version_ of the collection with this ID
    db_form = get_form_by_id(form_id, grant_id=grant_id)

    if db_form.section.collection.live_submissions:
        # Prevent changes to the task if it has any live submissions; this is very coarse layer of protection. We might
        # want to do something more fine-grained to give a better user experience at some point. And/or we might need
        # to allow _some_ people (eg platform admins) to make changes, at their own peril.
        # TODO: flash and redirect back to 'list report tasks'?
        current_app.logger.info(
            "Blocking access to manage form %(form_id)s because related collection has live submissions",
            dict(form_id=str(form_id)),
        )
        return abort(403)

    form = AddTaskForm(obj=db_form)
    if form.validate_on_submit():
        assert form.title.data
        try:
            update_form(db_form, title=form.title.data)
            return redirect(
                url_for(
                    "deliver_grant_funding.list_task_questions",
                    grant_id=grant_id,
                    form_id=db_form.id,
                )
            )
        except DuplicateValueError:
            # FIXME: standardise+consolidate how we handle form errors raised from interfaces
            form.title.errors.append("A task with this name already exists")  # type: ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/reports/change_form_name.html",
        grant=db_form.section.collection.grant,
        db_form=db_form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-name", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_group_name(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupForm(obj=db_group)
    if form.validate_on_submit():
        assert form.name.data
        try:
            update_group(db_group, name=form.name.data)
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except DuplicateValueError:
            form.name.errors.append("A question group with this name already exists")  # type: ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/reports/change_question_group_name.html",
        grant=db_group.form.section.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-display-options", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_group_display_options(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupDisplayOptionsForm(
        show_questions_on_the_same_page=GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        if db_group.presentation_options.show_questions_on_the_same_page
        else GroupDisplayOptions.ONE_QUESTION_PER_PAGE
    )
    if form.validate_on_submit():
        try:
            # todo: pass the result of checking if questions depend on each other
            #       into the template so that we can grey out the option before reaching this point
            #       will need to decide how thats displayed: p text before the radio might work - grey hint
            #       on grey hint bad
            update_group(db_group, presentation_options=QuestionPresentationOptions.from_group_form(form))
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except DependencyOrderException:
            form.show_questions_on_the_same_page.errors.append(  # type: ignore[attr-defined]
                "A question group cannot display on the same page if questions depend on answers within the group"
            )

    return render_template(
        "deliver_grant_funding/reports/change_question_group_display_options.html",
        grant=db_group.form.section.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/task/<uuid:form_id>/questions", methods=["GET", "POST"])
@has_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_task_questions(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id, grant_id=grant_id, with_all_questions=True)

    preview_form = GenericSubmitForm()
    if preview_form.validate_on_submit() and preview_form.submit.data:
        return start_testing_submission(db_form.section.collection, form=db_form)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.has_grant_role(grant_id, RoleEnum.ADMIN, user=get_current_user()):
            return redirect(url_for("deliver_grant_funding.list_task_questions", grant_id=grant_id, form_id=form_id))

        if db_form.section.collection.live_submissions:
            # Prevent changes to the task if it has any live submissions; this is very coarse layer of protection. We
            # might want to do something more fine-grained to give a better user experience at some point. And/or we
            # might need to allow _some_ people (eg platform admins) to make changes, at their own peril.
            # TODO: flash and redirect back to 'list report tasks'?
            current_app.logger.info(
                "Blocking access to delete form %(form_id)s because related collection has live submissions",
                dict(form_id=str(form_id)),
            )
            abort(403)

        if delete_wtform.validate_on_submit():
            delete_form(db_form)

            return redirect(
                url_for(
                    "deliver_grant_funding.list_report_tasks",
                    grant_id=grant_id,
                    report_id=db_form.section.collection_id,
                )
            )

    return render_template(
        "deliver_grant_funding/reports/list_task_questions.html",
        grant=db_form.section.collection.grant,
        db_form=db_form,
        delete_form=delete_wtform,
        form=preview_form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/questions", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_group_questions(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    group = get_group_by_id(group_id)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.has_grant_role(grant_id, RoleEnum.ADMIN, user=get_current_user()):
            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group_id))

        try:
            raise_if_question_has_any_dependencies(group)
            if delete_wtform.validate_on_submit() and delete_wtform.confirm_deletion.data:
                delete_question(group)

                return redirect(
                    url_for("deliver_grant_funding.list_task_questions", grant_id=grant_id, form_id=group.form_id)
                )
        except DependencyOrderException as e:
            flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type:ignore [arg-type]
            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group_id))

    return render_template(
        "deliver_grant_funding/reports/list_group_questions.html",
        grant=group.form.section.collection.grant,
        db_form=group.form,
        delete_form=delete_wtform,
        group=group,
    )


class AddQuestionGroup(BaseModel):
    group_name: str

    def to_session_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> "AddQuestionGroup":
        return cls.model_validate(session_data)


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/groups/add",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_group_name(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    group_name = request.args.get("name", None)

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    wt_form = GroupForm(name=group_name, check_name_exists=True, group_form_id=form_id)

    if wt_form.validate_on_submit():
        assert wt_form.name.data is not None
        session["add_question_group"] = AddQuestionGroup(group_name=wt_form.name.data).to_session_dict()
        return redirect(
            url_for(
                "deliver_grant_funding.add_question_group_display_options",
                grant_id=grant_id,
                form_id=form_id,
                parent_id=parent.id if parent else None,
            )
        )

    return render_template(
        "deliver_grant_funding/reports/add_question_group_name.html",
        grant=form.section.collection.grant,
        db_form=form,
        form=wt_form,
        parent=parent,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/groups/add/display_options",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_group_display_options(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    try:
        add_question_group = AddQuestionGroup.from_session(session.get("add_question_group", {}))
    except ValidationError:
        return redirect(
            url_for(
                "deliver_grant_funding.add_question_group_name",
                grant_id=grant_id,
                form_id=form_id,
                parent_id=parent.id if parent else None,
            )
        )

    wt_form = GroupDisplayOptionsForm()

    if wt_form.validate_on_submit():
        group = create_group(
            text=add_question_group.group_name,
            form=form,
            parent=parent,
            presentation_options=QuestionPresentationOptions.from_group_form(wt_form),
        )
        session.pop("add_question_group", None)
        return redirect(
            url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, form_id=form_id, group_id=group.id)
        )

    return render_template(
        "deliver_grant_funding/reports/add_question_group_display_options.html",
        grant=form.section.collection.grant,
        db_form=form,
        group_name=add_question_group.group_name,
        form=wt_form,
        parent=parent,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/question/<uuid:component_id>/move-<direction>")
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def move_component(grant_id: UUID, component_id: UUID, direction: str) -> ResponseReturnValue:
    component = get_component_by_id(component_id)

    try:
        match direction:
            case "up":
                move_component_up(component)
            case "down":
                move_component_down(component)
            case _:
                return abort(400)
    except DependencyOrderException as e:
        flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type: ignore[arg-type]

    source = request.args.get("source", None)
    if source:
        return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=source))
    else:
        return redirect(
            url_for("deliver_grant_funding.list_task_questions", grant_id=grant_id, form_id=component.form_id)
        )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/questions/add/choose-type",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
def choose_question_type(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))
    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data
        return redirect(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant_id,
                form_id=form_id,
                question_data_type=question_data_type,
                parent_id=parent_id if parent else None,
            )
        )

    return render_template(
        "deliver_grant_funding/reports/choose_question_type.html",
        grant=db_form.section.collection.grant,
        db_form=db_form,
        form=wt_form,
        parent=parent,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    question_data_type_arg = request.args.get("question_data_type", QuestionDataType.TEXT_SINGLE_LINE.name)
    question_data_type_enum = QuestionDataType.coerce(question_data_type_arg)
    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    wt_form = QuestionForm(question_type=question_data_type_enum)
    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None

            question = create_question(
                form=form,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                data_type=question_data_type_enum,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions.from_question_form(wt_form),
                parent=parent,
            )
            flash("Question created", FlashMessageType.QUESTION_CREATED)
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/reports/add_question.html",
        grant=form.section.collection.grant,
        collection=form.section.collection,
        section=form.section,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
        parent=parent,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def edit_question(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    # FIXME: It would be better if the add_question and edit_question endpoints were an all-in-one. The complication
    #        for doing this is around adding conditions and validations when creating a new question. At the moment
    #        both of those endpoints expect to attach it to an existing question in the DB, but through an
    #        'add question' flow that question record doesn't exist yet. We'd need to cache info about
    #        validation+conditions that need to be added to the question, when the question itself is created.
    question = get_question_by_id(question_id=question_id)
    wt_form = QuestionForm(obj=question, question_type=question.data_type)

    confirm_deletion_form = GenericConfirmDeletionForm()
    if "delete" in request.args:
        try:
            raise_if_question_has_any_dependencies(question)

            if confirm_deletion_form.validate_on_submit() and confirm_deletion_form.confirm_deletion.data:
                delete_question(question)
                return redirect(
                    url_for("deliver_grant_funding.list_task_questions", grant_id=grant_id, form_id=question.form_id)
                )

        except DependencyOrderException as e:
            flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type:ignore [arg-type]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    form_id=question.form_id,
                    question_id=question_id,
                )
            )

    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            update_question(
                question=question,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions.from_question_form(wt_form),
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_task_questions",
                    grant_id=grant_id,
                    form_id=question.form_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
        except DataSourceItemReferenceDependencyException as e:
            for flash_context in e.as_flash_contexts():
                flash(flash_context, FlashMessageType.DATA_SOURCE_ITEM_DEPENDENCY_ERROR.value)  # type: ignore[arg-type]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    form_id=question.form_id,
                    question_id=question_id,
                )
            )

    return render_template(
        "deliver_grant_funding/reports/edit_question.html",
        grant=question.form.section.collection.grant,
        db_form=question.form,
        question=question,
        form=wt_form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        managed_validation_available=get_managed_validators_by_data_type(question.data_type),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/guidance", methods=["GET", "POST"]
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def manage_guidance(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_component_by_id(component_id=question_id)
    form = AddGuidanceForm(obj=question)

    if form.validate_on_submit():
        # todo: both of these are equivalent as this is a property of the underlying component
        #       should there be an update that handles either
        if question.is_group:
            update_group(
                cast("Group", question),
                guidance_heading=form.guidance_heading.data,
                guidance_body=form.guidance_body.data,
            )
        else:
            update_question(
                cast("Question", question),
                guidance_heading=form.guidance_heading.data,
                guidance_body=form.guidance_body.data,
            )

        if form.preview.data:
            return redirect(
                url_for(
                    "deliver_grant_funding.manage_guidance",
                    grant_id=grant_id,
                    question_id=question_id,
                    _anchor="preview-guidance",
                )
            )

        return redirect(
            url_for("deliver_grant_funding.edit_question", grant_id=grant_id, question_id=question_id)
            if not question.is_group
            else url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=question.id)
        )

    return render_template(
        "deliver_grant_funding/reports/manage_guidance.html",
        grant=question.form.section.collection.grant,
        question=question,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
def add_question_condition_select_question(grant_id: UUID, component_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id)
    form = ConditionSelectQuestionForm(question=component)

    if form.validate_on_submit():
        depends_on_question = get_question_by_id(form.question.data)
        return redirect(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=grant_id,
                component_id=component_id,
                depends_on_question_id=depends_on_question.id,
            )
        )

    return render_template(
        "deliver_grant_funding/reports/add_question_condition_select_question.html",
        component=component,
        grant=component.form.section.collection.grant,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition/<uuid:depends_on_question_id>",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_condition(grant_id: UUID, component_id: UUID, depends_on_question_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id)
    depends_on_question = get_question_by_id(depends_on_question_id)

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
    form = ConditionForm() if ConditionForm else None
    if form and form.validate_on_submit():
        expression = form.get_expression(depends_on_question)

        try:
            interfaces.collections.add_component_condition(component, interfaces.user.get_current_user(), expression)
            if component.is_group:
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_group_questions",
                        grant_id=grant_id,
                        group_id=component.id,
                    )
                )
            else:
                return redirect(
                    url_for(
                        "deliver_grant_funding.edit_question",
                        grant_id=grant_id,
                        question_id=component.id,
                    )
                )
        except DuplicateValueError:
            form.form_errors.append(f"“{expression.description}” condition based on this question already exists.")

    return render_template(
        "deliver_grant_funding/reports/manage_question_condition_select_condition_type.html",
        component=component,
        depends_on_question=depends_on_question,
        grant=component.form.section.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/condition/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def edit_question_condition(grant_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    expression = get_expression_by_id(expression_id)
    component = expression.question
    depends_on_question = expression.managed.referenced_question

    return_url = (
        url_for("deliver_grant_funding.edit_question", grant_id=grant_id, question_id=component.id)
        if not component.is_group
        else url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=component.id)
    )

    confirm_deletion_form = GenericConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=component, expression=expression)
        return redirect(return_url)

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question, expression)
    form = ConditionForm() if ConditionForm else None

    if form and form.validate_on_submit():
        updated_managed_expression = form.get_expression(depends_on_question)

        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
            return redirect(return_url)
        except DuplicateValueError:
            form.form_errors.append(
                f"“{updated_managed_expression.description}” condition based on this question already exists."
            )

    return render_template(
        "deliver_grant_funding/reports/manage_question_condition_select_condition_type.html",
        component=component,
        grant=component.form.section.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
        depends_on_question=depends_on_question,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/add-validation",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_validation(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)

    ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
    form = ValidationForm() if ValidationForm else None
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
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    return render_template(
        "deliver_grant_funding/reports/manage_question_validation.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/validation/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def edit_question_validation(grant_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    expression = get_expression_by_id(expression_id)
    question = expression.question

    confirm_deletion_form = GenericConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=question, expression=expression)
        return redirect(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant_id,
                question_id=question.id,
            )
        )

    # anything we're depending on will currently definitely be a question component
    ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, cast("Question", question), expression)
    form = ValidationForm() if ValidationForm else None

    if form and form.validate_on_submit():
        # todo: any time we're dealing with the dependant component its a question - make sure this makes sense
        updated_managed_expression = form.get_expression(cast("Question", question))
        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(
                f"“{updated_managed_expression.description}” validation already exists on the question."
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    return render_template(
        "deliver_grant_funding/reports/manage_question_validation.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/report/<uuid:report_id>/submissions/<submission_mode:submission_mode>"
)
@has_grant_role(RoleEnum.MEMBER)
def list_submissions(grant_id: UUID, report_id: UUID, submission_mode: SubmissionModeEnum) -> ResponseReturnValue:
    report = interfaces.collections.get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)
    helper = CollectionHelper(collection=report, submission_mode=submission_mode)

    return render_template(
        "deliver_grant_funding/reports/list_submissions.html",
        grant=report.grant,
        report=report,
        helper=helper,
        submission_mode=submission_mode,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/report/<uuid:report_id>/submissions/<submission_mode:submission_mode>/export/<export_format>",
    methods=["GET"],
)
@has_grant_role(RoleEnum.MEMBER)
def export_report_submissions(
    grant_id: UUID, report_id: UUID, submission_mode: SubmissionModeEnum, export_format: str
) -> ResponseReturnValue:
    report = interfaces.collections.get_collection(
        report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT, with_full_schema=True
    )
    helper = CollectionHelper(collection=report, submission_mode=submission_mode)

    export_format = export_format.lower()
    match export_format:
        case "csv":
            data = helper.generate_csv_content_for_all_submissions()
            mimetype = "text/csv"

        case "json":
            data = helper.generate_json_content_for_all_submissions()
            mimetype = "application/json"

        case _:
            abort(400)

    buffer = io.StringIO()
    buffer.write(data)
    buffer.seek(0)
    return send_file(
        io.BytesIO(buffer.getvalue().encode("utf-8")),
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"{report.name} - {submission_mode.name.lower()}.{export_format}",
        max_age=0,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/submission/<uuid:submission_id>")
@has_grant_role(RoleEnum.MEMBER)
def view_submission(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    helper = SubmissionHelper.load(submission_id)
    return render_template(
        "deliver_grant_funding/reports/view_submission.html",
        grant=helper.grant,
        helper=helper,
    )
