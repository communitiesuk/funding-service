import io
import uuid
from typing import TYPE_CHECKING, Any, Optional, cast
from uuid import UUID

from flask import abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from flask.typing import ResponseReturnValue
from pydantic import BaseModel, ValidationError
from wtforms import Field

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_deliver_grant_role
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    AddAnotherDependencyException,
    AddAnotherNotValidException,
    DataSourceItemReferenceDependencyException,
    DependencyOrderException,
    GroupContainsAddAnotherException,
    NestedGroupDisplayTypeSamePageException,
    NestedGroupException,
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
    raise_if_nested_group_creation_not_valid_here,
    raise_if_question_has_any_dependencies,
    remove_question_expression,
    update_collection,
    update_form,
    update_group,
    update_question,
)
from app.common.data.interfaces.exceptions import (
    DuplicateValueError,
    InvalidReferenceInExpression,
)
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import (
    CollectionType,
    ExpressionType,
    GroupDisplayOptions,
    ManagedExpressionsEnum,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.forms import _ManagedExpressionForm, build_managed_expression_form
from app.common.expressions.registry import get_managed_validators_by_data_type, lookup_managed_expression
from app.common.forms import GenericConfirmDeletionForm, GenericSubmitForm
from app.common.helpers.collections import CollectionHelper, SubmissionHelper
from app.deliver_grant_funding.forms import (
    AddContextSelectSourceForm,
    AddGuidanceForm,
    AddTaskForm,
    ConditionSelectQuestionForm,
    GroupAddAnotherOptionsForm,
    GroupAddAnotherSummaryForm,
    GroupDisplayOptionsForm,
    GroupForm,
    QuestionForm,
    QuestionTypeForm,
    SelectDataSourceQuestionForm,
    SetUpReportForm,
)
from app.deliver_grant_funding.helpers import start_testing_submission
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.deliver_grant_funding.session_models import (
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
)
from app.extensions import auto_commit_after_request
from app.types import NOT_PROVIDED, FlashMessageType, TNotProvided

if TYPE_CHECKING:
    from app.common.data.models import Expression, Group, Question


SessionModelType = (
    AddContextToComponentSessionModel | AddContextToComponentGuidanceSessionModel | AddContextToExpressionsModel
)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/reports", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_reports(grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)

    delete_wtform, delete_report = None, None
    if delete_report_id := request.args.get("delete"):
        if not AuthorisationHelper.has_deliver_grant_role(grant_id, RoleEnum.ADMIN, user=get_current_user()):
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
@has_deliver_grant_role(RoleEnum.ADMIN)
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
@has_deliver_grant_role(RoleEnum.ADMIN)
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
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_report_tasks(grant_id: UUID, report_id: UUID) -> ResponseReturnValue:
    report = get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT, with_full_schema=True)
    form = GenericSubmitForm()

    if form.validate_on_submit() and form.submit.data:
        return start_testing_submission(collection=report)

    return render_template(
        "deliver_grant_funding/reports/list_report_tasks.html",
        grant=report.grant,
        report=report,
        form=form,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/form/<uuid:form_id>/move-<direction>")
@has_deliver_grant_role(RoleEnum.ADMIN)
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

    return redirect(url_for("deliver_grant_funding.list_report_tasks", grant_id=grant_id, report_id=form.collection_id))


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/report/<uuid:report_id>/add-task", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
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

    form = AddTaskForm(obj=report)
    if form.validate_on_submit():
        assert form.title.data
        try:
            create_form(
                title=form.title.data,
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
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_form_name(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    # NOTE: this fetches the _latest version_ of the collection with this ID
    db_form = get_form_by_id(form_id, grant_id=grant_id)

    if db_form.collection.live_submissions:
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
        grant=db_form.collection.grant,
        db_form=db_form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-name", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_group_name(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupForm(obj=db_group)
    if form.validate_on_submit():
        assert form.name.data
        try:
            update_group(
                db_group,
                expression_context=ExpressionContext.build_expression_context(
                    collection=db_group.form.collection, mode="interpolation"
                ),
                name=form.name.data,
            )
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
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-display-options", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
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
            update_group(
                db_group,
                expression_context=ExpressionContext.build_expression_context(
                    collection=db_group.form.collection, mode="interpolation"
                ),
                presentation_options=QuestionPresentationOptions.from_group_form(form),
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except DependencyOrderException:
            # TODO: can we show the user the problematic questions like we do when rendering flashable exceptions?
            form.show_questions_on_the_same_page.errors.append(  # type: ignore[attr-defined]
                "A question group cannot display on the same page if questions depend on answers within the group"
            )
        except NestedGroupDisplayTypeSamePageException:
            form.show_questions_on_the_same_page.errors.append(  # type: ignore[attr-defined]
                "A question group cannot display on the same page if it contains a nested group"
            )

    return render_template(
        "deliver_grant_funding/reports/change_question_group_display_options.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-add-another-summary", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_group_add_another_summary(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)
    form = GroupAddAnotherSummaryForm(group=db_group)

    if form.validate_on_submit():
        update_group(
            db_group,
            expression_context=ExpressionContext.build_expression_context(
                collection=db_group.form.collection, mode="interpolation"
            ),
            presentation_options=QuestionPresentationOptions(
                add_another_summary_line_question_ids=form.questions_to_show_in_add_another_summary.data
            ),
        )
        return redirect(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=grant_id,
                group_id=db_group.id,
            )
        )

    return render_template(
        "deliver_grant_funding/reports/change_question_group_add_another_summary.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-add-another-options", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def change_group_add_another_options(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupAddAnotherOptionsForm(question_group_is_add_another="yes" if db_group.add_another else "no")
    if form.validate_on_submit():
        try:
            # todo: pass the result of checking if questions depend on each other
            #       into the template so that we can grey out the option before reaching this point
            #       will need to decide how thats displayed: p text before the radio might work - grey hint
            #       on grey hint bad
            update_group(
                db_group,
                expression_context=ExpressionContext.build_expression_context(
                    collection=db_group.form.collection, mode="interpolation"
                ),
                add_another=True if form.question_group_is_add_another.data == "yes" else False,
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except GroupContainsAddAnotherException:
            form.question_group_is_add_another.errors.append(  # type:ignore[attr-defined]
                "A question group cannot be answered more than once if it already contains questions that can "
                "be answered more than once"
            )
        except AddAnotherDependencyException:
            form.question_group_is_add_another.errors.append(  # type:ignore[attr-defined]
                "A question group cannot be answered more than once if questions elsewhere in the form depend on "
                "questions in this group"
            )
        except AddAnotherNotValidException:
            form.question_group_is_add_another.errors.append(  # type:ignore[attr-defined]
                "A question group cannot be answered more than once if it is already inside a group that can "
                "be answered more than once"
            )

    return render_template(
        "deliver_grant_funding/reports/change_question_group_add_another_options.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/task/<uuid:form_id>/questions", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_task_questions(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id, grant_id=grant_id, with_all_questions=True)

    preview_form = GenericSubmitForm()
    if preview_form.validate_on_submit() and preview_form.submit.data:
        return start_testing_submission(db_form.collection, form=db_form)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.has_deliver_grant_role(grant_id, RoleEnum.ADMIN, user=get_current_user()):
            return redirect(url_for("deliver_grant_funding.list_task_questions", grant_id=grant_id, form_id=form_id))

        if db_form.collection.live_submissions:
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
                    report_id=db_form.collection_id,
                )
            )

    return render_template(
        "deliver_grant_funding/reports/list_task_questions.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        delete_form=delete_wtform,
        form=preview_form,
        interpolate=SubmissionHelper.get_interpolator(collection=db_form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/questions", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_group_questions(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    group = get_group_by_id(group_id)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.has_deliver_grant_role(grant_id, RoleEnum.ADMIN, user=get_current_user()):
            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group_id))

        try:
            raise_if_question_has_any_dependencies(group)
            if delete_wtform.validate_on_submit() and delete_wtform.confirm_deletion.data:
                delete_question(group)
                if group.parent and group.parent.is_group:
                    return redirect(
                        url_for(
                            "deliver_grant_funding.list_group_questions",
                            grant_id=grant_id,
                            group_id=group.parent.id,
                        )
                    )
                return redirect(
                    url_for("deliver_grant_funding.list_task_questions", grant_id=grant_id, form_id=group.form_id)
                )
        except DependencyOrderException as e:
            flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type:ignore [arg-type]
            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group_id))

    return render_template(
        "deliver_grant_funding/reports/list_group_questions.html",
        grant=group.form.collection.grant,
        db_form=group.form,
        delete_form=delete_wtform,
        group=group,
        interpolate=SubmissionHelper.get_interpolator(collection=group.form.collection),
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
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_group_name(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    group_name = request.args.get("name", None)

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    if parent:
        try:
            raise_if_nested_group_creation_not_valid_here(parent=parent)
        except (NestedGroupException, NestedGroupDisplayTypeSamePageException) as e:
            flash(e.as_flash_context(), FlashMessageType.NESTED_GROUP_ERROR.value)  # type: ignore[arg-type]
            return redirect(
                url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=parent.id)
            )

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
        grant=form.collection.grant,
        db_form=form,
        form=wt_form,
        parent=parent,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/groups/add/display_options",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
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
        try:
            group = create_group(
                text=add_question_group.group_name,
                form=form,
                parent=parent,
                presentation_options=QuestionPresentationOptions.from_group_form(wt_form),
            )
            session.pop("add_question_group", None)
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions", grant_id=grant_id, form_id=form_id, group_id=group.id
                )
            )
        except NestedGroupDisplayTypeSamePageException as e:
            flash(e.as_flash_context(), FlashMessageType.NESTED_GROUP_ERROR.value)  # type: ignore[arg-type]
        except NestedGroupException as e:
            flash(e.as_flash_context(), FlashMessageType.NESTED_GROUP_ERROR.value)  # type: ignore[arg-type]

    return render_template(
        "deliver_grant_funding/reports/add_question_group_display_options.html",
        grant=form.collection.grant,
        db_form=form,
        group_name=add_question_group.group_name,
        form=wt_form,
        parent=parent,
        interpolate=SubmissionHelper.get_interpolator(collection=form.collection),
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/question/<uuid:component_id>/move-<direction>")
@has_deliver_grant_role(RoleEnum.ADMIN)
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
@has_deliver_grant_role(RoleEnum.ADMIN)
def choose_question_type(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))
    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data

        if "question" in session:
            del session["question"]

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
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wt_form,
        parent=parent,
    )


def _extract_add_context_data_from_session(
    session_model: type[SessionModelType] | None = None,
    question_id: UUID | TNotProvided | None = NOT_PROVIDED,
    expression_id: UUID | TNotProvided | None = NOT_PROVIDED,
) -> SessionModelType | None:
    add_context_data: SessionModelType | None = None
    if session_data := session.get("question"):
        match session_data["field"]:
            case "component":
                add_context_data = AddContextToComponentSessionModel(**session_data)  # ty: ignore[missing-argument]
                if question_id is not NOT_PROVIDED and question_id != add_context_data.component_id:
                    del session["question"]
                    return None

            case "guidance":
                add_context_data = AddContextToComponentGuidanceSessionModel(**session_data)  # ty: ignore[missing-argument]
                if question_id is not NOT_PROVIDED and question_id != add_context_data.component_id:
                    del session["question"]
                    return None

            case ExpressionType.CONDITION | ExpressionType.VALIDATION:
                add_context_data = AddContextToExpressionsModel(**session_data)  # ty: ignore[missing-argument]
                if (question_id is not NOT_PROVIDED and question_id != add_context_data.component_id) or (
                    expression_id is not NOT_PROVIDED and expression_id != add_context_data.expression_id
                ):
                    del session["question"]
                    return None

                managed_expression_cls = lookup_managed_expression(add_context_data.managed_expression_name)
                add_context_data._prepared_form_data = managed_expression_cls.prepare_form_data(add_context_data)
                # Populate the `type` of the form from `build_managed_expression_form` so that the general
                # ManagedExpression selection is preserved.
                add_context_data._prepared_form_data["type"] = add_context_data.managed_expression_name

            case _:
                raise ValueError(f"Unexpected field type: {session_data['field']}")
    else:
        return None

    if add_context_data and session_model and not isinstance(add_context_data, session_model):
        del session["question"]
        return None

    return add_context_data


def _store_question_state_and_redirect_to_add_context(
    form: QuestionForm | AddGuidanceForm | _ManagedExpressionForm,
    grant_id: UUID,
    form_id: UUID,
    question_id: UUID | None = None,
    parent_id: UUID | None = None,
    form_data: dict[str, Any] | None = None,
    expression_type: ExpressionType | None = None,
    managed_expression_name: ManagedExpressionsEnum | None = None,
    expression_id: UUID | None = None,
    depends_on_question_id: UUID | None = None,
    is_add_another_guidance: bool | None = False,
) -> ResponseReturnValue:
    add_context_data: SessionModelType
    match form:
        case QuestionForm():
            add_context_data = AddContextToComponentSessionModel(
                data_type=form._question_type,
                component_form_data=cast(dict[str, Any], form_data),
                component_id=question_id,
                parent_id=parent_id,
            )
        case AddGuidanceForm():
            if question_id is None:
                raise ValueError()
            add_context_data = AddContextToComponentGuidanceSessionModel(
                component_form_data=cast(dict[str, Any], form_data),
                component_id=question_id,
                is_add_another_guidance=is_add_another_guidance,
            )
        case _ManagedExpressionForm():
            add_context_data = AddContextToExpressionsModel(  # type: ignore[call-arg]
                field=expression_type,  # type: ignore[arg-type]
                managed_expression_name=managed_expression_name,  # type: ignore[arg-type]
                expression_form_data=form_data,  # type: ignore[arg-type]
                component_id=question_id,  # type: ignore[arg-type]
                expression_id=expression_id,
                depends_on_question_id=depends_on_question_id,
            )
        case _:
            raise ValueError(f"Unexpected form type: {form}")
    # TODO: define a parent pydantic model for all of our session context
    session["question"] = add_context_data.model_dump(mode="json")
    return redirect(
        url_for("deliver_grant_funding.select_context_source", grant_id=grant_id, form_id=form_id, parent_id=parent_id)
    )


def _handle_remove_context_for_expression_forms(
    form: _ManagedExpressionForm,
    component_id: UUID,
    expression_type: ExpressionType,
    expression: Optional["Expression"] = None,
    add_context_data: AddContextToExpressionsModel | None = None,
    depends_on_question_id: UUID | None = None,
) -> None:
    field_to_clear = form.remove_context.data  # ty: ignore[unresolved-attribute]
    if not field_to_clear:
        return

    form_data = form.get_expression_form_data()

    if not add_context_data:
        if not expression:
            raise ValueError("Expression required when add_context_data is None")

        add_context_data = AddContextToExpressionsModel(
            _prepared_form_data={},
            field=expression_type,
            managed_expression_name=expression.managed_name,  # type: ignore[arg-type]
            expression_form_data=form_data,
            component_id=component_id,
            expression_id=expression.id,
            depends_on_question_id=depends_on_question_id,
        )
    else:
        add_context_data.expression_form_data.update(form_data)

    add_context_data.expression_form_data[field_to_clear] = ""

    if expression:
        add_context_data._prepared_form_data = expression.managed.prepare_form_data(add_context_data)
        add_context_data._prepared_form_data["type"] = expression.managed_name
    else:
        managed_expression = lookup_managed_expression(add_context_data.managed_expression_name)
        add_context_data._prepared_form_data = managed_expression.prepare_form_data(add_context_data)
        add_context_data._prepared_form_data["type"] = add_context_data.managed_expression_name

    session["question"] = add_context_data.model_dump(mode="json")


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    question_data_type_arg = request.args.get("question_data_type", QuestionDataType.TEXT_SINGLE_LINE.name)
    question_data_type_enum = QuestionDataType.coerce(question_data_type_arg)
    raw_parent_id = request.args.get("parent_id", None)
    parent_id = UUID(raw_parent_id) if raw_parent_id else None
    parent = get_group_by_id(parent_id) if parent_id else None

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentSessionModel, question_id=None
    )

    wt_form = QuestionForm(
        data=add_context_data.component_form_data if add_context_data else None,  # type: ignore[union-attr]
        question_type=question_data_type_enum,
    )

    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            wt_form, grant_id=grant_id, form_id=form_id, parent_id=parent_id, form_data=form_data
        )

    elif wt_form.validate_on_submit():
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
                expression_context=ExpressionContext.build_expression_context(
                    collection=form.collection, mode="interpolation"
                ),
                parent=parent,
            )
            flash("Question created", FlashMessageType.QUESTION_CREATED)

            if "question" in session:
                del session["question"]

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
        except InvalidReferenceInExpression as e:
            field_with_error = getattr(wt_form, e.field_name)
            field_with_error.errors.append(e.message)  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/reports/add_question.html",
        grant=form.collection.grant,
        collection=form.collection,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
        parent=parent,
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(collection=form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/add-context/select-source", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
def select_context_source(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    wtform = AddContextSelectSourceForm(
        form=db_form,
        current_component=get_component_by_id(add_context_data.component_id) if add_context_data.component_id else None,
    )
    if wtform.validate_on_submit():
        add_context_data.data_source = ExpressionContext.ContextSources[wtform.data_source.data]
        session["question"] = add_context_data.model_dump(mode="json")

        match add_context_data.data_source:
            case ExpressionContext.ContextSources.TASK:
                return redirect(
                    url_for("deliver_grant_funding.select_context_source_question", grant_id=grant_id, form_id=form_id)
                )

            case _:
                abort(500)

    return render_template(
        "deliver_grant_funding/reports/select_context_source.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wtform,
        add_context_data=add_context_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/task/<uuid:form_id>/add-context/select-question-from-task", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
def select_context_source_question(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)

    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    # TODO: Add depends_on_question_id as a nullable attribute to all session models to simplify this check?
    current_component = (
        get_component_by_id(add_context_data.depends_on_question_id)  # type: ignore[union-attr, arg-type]
        if getattr(add_context_data, "depends_on_question_id", None)
        else get_component_by_id(add_context_data.component_id)
        if add_context_data.component_id
        else None
    )

    wtform = SelectDataSourceQuestionForm(
        form=db_form,
        interpolate=SubmissionHelper.get_interpolator(collection=db_form.collection),
        current_component=current_component,
        expression=isinstance(add_context_data, AddContextToExpressionsModel),
    )

    if wtform.validate_on_submit():
        referenced_question = get_question_by_id(UUID(wtform.question.data))
        match add_context_data:
            case AddContextToComponentSessionModel():
                return_url = (
                    url_for(
                        "deliver_grant_funding.add_question",
                        grant_id=grant_id,
                        form_id=form_id,
                        parent_id=add_context_data.parent_id,
                        question_data_type=add_context_data.data_type.name,
                    )
                    if add_context_data.component_id is None
                    else url_for(
                        "deliver_grant_funding.edit_question",
                        grant_id=grant_id,
                        question_id=add_context_data.component_id,
                    )
                )

                if add_context_data and isinstance(add_context_data, AddContextToComponentSessionModel):
                    target_field = add_context_data.component_form_data["add_context"]
                    add_context_data.component_form_data[target_field] += f" (({referenced_question.safe_qid}))"

            case AddContextToComponentGuidanceSessionModel():
                return_url = (
                    url_for(
                        "deliver_grant_funding.manage_guidance",
                        grant_id=grant_id,
                        question_id=add_context_data.component_id,
                    )
                    if add_context_data.is_add_another_guidance is False
                    else url_for(
                        "deliver_grant_funding.manage_add_another_guidance",
                        grant_id=grant_id,
                        group_id=add_context_data.component_id,
                    )
                )
                if add_context_data and isinstance(add_context_data, AddContextToComponentGuidanceSessionModel):
                    target_field = add_context_data.component_form_data["add_context"]
                    add_context_data.component_form_data[target_field] += f" (({referenced_question.safe_qid}))"

            case AddContextToExpressionsModel():
                if add_context_data and isinstance(add_context_data, AddContextToExpressionsModel):
                    target_field = add_context_data.expression_form_data["add_context"]
                    add_context_data.expression_form_data[target_field] = f"(({referenced_question.safe_qid}))"

                if add_context_data.field == ExpressionType.CONDITION:
                    if not add_context_data.expression_id:
                        return_url = url_for(
                            "deliver_grant_funding.add_question_condition",
                            grant_id=grant_id,
                            component_id=add_context_data.component_id,
                            depends_on_question_id=add_context_data.depends_on_question_id,
                        )
                    else:
                        return_url = url_for(
                            "deliver_grant_funding.edit_question_condition",
                            grant_id=grant_id,
                            expression_id=add_context_data.expression_id,
                        )
                else:
                    if not add_context_data.expression_id:
                        return_url = url_for(
                            "deliver_grant_funding.add_question_validation",
                            grant_id=grant_id,
                            question_id=add_context_data.component_id,
                        )
                    else:
                        return_url = url_for(
                            "deliver_grant_funding.edit_question_validation",
                            grant_id=grant_id,
                            expression_id=add_context_data.expression_id,
                        )

        session["question"] = add_context_data.model_dump(mode="json")
        return redirect(return_url)

    return render_template(
        "deliver_grant_funding/reports/select_context_source_question.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wtform,
        add_context_data=add_context_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def edit_question(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:  # noqa: C901
    # FIXME: It would be better if the add_question and edit_question endpoints were an all-in-one. The complication
    #        for doing this is around adding conditions and validations when creating a new question. At the moment
    #        both of those endpoints expect to attach it to an existing question in the DB, but through an
    #        'add question' flow that question record doesn't exist yet. We'd need to cache info about
    #        validation+conditions that need to be added to the question, when the question itself is created.
    question = get_question_by_id(question_id=question_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentSessionModel, question_id=question_id
    )

    wt_form = QuestionForm(
        obj=question if not add_context_data else None,
        data=add_context_data.component_form_data if add_context_data else None,  # type: ignore[union-attr]
        question_type=question.data_type,
    )

    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            wt_form, grant_id=grant_id, form_id=question.form_id, question_id=question.id, form_data=form_data
        )

    confirm_deletion_form = GenericConfirmDeletionForm()
    if "delete" in request.args:
        try:
            raise_if_question_has_any_dependencies(question)

            if confirm_deletion_form.validate_on_submit() and confirm_deletion_form.confirm_deletion.data:
                delete_question(question)
                if question.parent and question.parent.is_group:
                    return redirect(
                        url_for(
                            "deliver_grant_funding.list_group_questions",
                            grant_id=grant_id,
                            group_id=question.parent.id,
                        )
                    )
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
                expression_context=ExpressionContext.build_expression_context(
                    collection=question.form.collection, mode="interpolation"
                ),
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions.from_question_form(wt_form),
            )

            if "question" in session:
                del session["question"]

            if question.parent and question.parent.is_group:
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_group_questions",
                        grant_id=grant_id,
                        group_id=question.parent.id,
                    )
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
        except InvalidReferenceInExpression as e:
            field_with_error = getattr(wt_form, e.field_name)
            field_with_error.errors.append(e.message)  # type:ignore[attr-defined]
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
        grant=question.form.collection.grant,
        db_form=question.form,
        question=question,
        form=wt_form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        managed_validation_available=get_managed_validators_by_data_type(question.data_type),
        interpolate=SubmissionHelper.get_interpolator(collection=question.form.collection),
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(
            collection=question.form.collection, expression_context_end_point=question
        ),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/add_another_guidance", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def manage_add_another_guidance(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    group = get_component_by_id(component_id=group_id)
    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentGuidanceSessionModel, question_id=group_id
    )

    form = AddGuidanceForm(
        data=add_context_data.component_form_data if add_context_data else None,  # type: ignore[union-attr]
        heading_required=False,
    )
    if not add_context_data and not form.is_submitted():
        form.guidance_body.data = group.add_another_guidance_body

    if form.is_submitted_to_add_context():
        form_data = form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form,
            grant_id=grant_id,
            form_id=group.form_id,
            question_id=group_id,
            form_data=form_data,
            is_add_another_guidance=True,
        )

    if form.validate_on_submit():
        try:
            update_group(
                cast("Group", group),
                expression_context=ExpressionContext.build_expression_context(
                    collection=group.form.collection, mode="interpolation"
                ),
                add_another_guidance_body=form.guidance_body.data,
            )

            if "question" in session:
                del session["question"]

            if form.preview.data:
                return redirect(
                    url_for(
                        "deliver_grant_funding.manage_add_another_guidance",
                        grant_id=grant_id,
                        group_id=group_id,
                        _anchor="preview-guidance",
                    )
                )

            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group.id))

        except InvalidReferenceInExpression as e:
            field_with_error = getattr(form, e.field_name)
            field_with_error.errors.append(e.message)

    return render_template(
        "deliver_grant_funding/reports/manage_add_another_guidance.html",
        grant=group.form.collection.grant,
        question=group,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(collection=group.form.collection),
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(
            collection=group.form.collection, expression_context_end_point=group
        ),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/guidance", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def manage_guidance(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_component_by_id(component_id=question_id)
    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentGuidanceSessionModel, question_id=question_id
    )

    form = AddGuidanceForm(
        obj=question if not add_context_data else None,
        data=add_context_data.component_form_data if add_context_data else None,  # type: ignore[union-attr]
    )

    if form.is_submitted_to_add_context():
        form_data = form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form,
            grant_id=grant_id,
            form_id=question.form_id,
            question_id=question_id,
            form_data=form_data,
        )

    if form.validate_on_submit():
        try:
            # todo: both of these are equivalent as this is a property of the underlying component
            #       should there be an update that handles either
            if question.is_group:
                update_group(
                    cast("Group", question),
                    expression_context=ExpressionContext.build_expression_context(
                        collection=question.form.collection, mode="interpolation"
                    ),
                    guidance_heading=form.guidance_heading.data,
                    guidance_body=form.guidance_body.data,
                )
            else:
                update_question(
                    cast("Question", question),
                    expression_context=ExpressionContext.build_expression_context(
                        collection=question.form.collection, mode="interpolation"
                    ),
                    guidance_heading=form.guidance_heading.data,
                    guidance_body=form.guidance_body.data,
                )

            if "question" in session:
                del session["question"]

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

        except InvalidReferenceInExpression as e:
            field_with_error = getattr(form, e.field_name)
            field_with_error.errors.append(e.message)

    # Build expression context for reference mappings
    return render_template(
        "deliver_grant_funding/reports/manage_guidance.html",
        grant=question.form.collection.grant,
        question=question,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(collection=question.form.collection),
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(
            collection=question.form.collection, expression_context_end_point=question
        ),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
def add_question_condition_select_question(grant_id: UUID, component_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id)
    form = ConditionSelectQuestionForm(
        current_component=component,
        interpolate=SubmissionHelper.get_interpolator(collection=component.form.collection),
    )

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
        grant=component.form.collection.grant,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition/<uuid:depends_on_question_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_condition(grant_id: UUID, component_id: UUID, depends_on_question_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id)
    depends_on_question = get_question_by_id(depends_on_question_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, question_id=component_id
    )

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
    form = (
        ConditionForm(data=add_context_data._prepared_form_data if add_context_data else None)  # type: ignore[union-attr]
        if ConditionForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=component.form.id,
            question_id=component.id,
            form_data=form_data,
            expression_type=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
            depends_on_question_id=depends_on_question_id,
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=component.id,
            expression_type=ExpressionType.CONDITION,
            add_context_data=add_context_data,  # type: ignore[arg-type]
            depends_on_question_id=depends_on_question_id,
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        expression = form.get_expression(depends_on_question)

        try:
            interfaces.collections.add_component_condition(component, interfaces.user.get_current_user(), expression)
        except DuplicateValueError:
            form.form_errors.append(f"“{expression.description}” condition based on this question already exists.")
        else:
            if "question" in session:
                del session["question"]

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

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=component.form.collection, expression_context_end_point=component
    )

    return render_template(
        "deliver_grant_funding/reports/manage_question_condition_select_condition_type.html",
        component=component,
        depends_on_question=depends_on_question,
        grant=component.form.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/condition/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
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

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, question_id=component.id, expression_id=expression_id
    )

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question, expression)
    form = (
        ConditionForm(data=add_context_data._prepared_form_data if add_context_data else None)  # type: ignore[union-attr]
        if ConditionForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=component.form.id,
            question_id=component.id,
            form_data=form_data,
            expression_type=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
            depends_on_question_id=depends_on_question.id,
            expression_id=expression_id,
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=component.id,
            expression_type=ExpressionType.CONDITION,
            expression=expression,
            add_context_data=add_context_data,  # type: ignore[arg-type]
            depends_on_question_id=depends_on_question.id,
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        updated_managed_expression = form.get_expression(depends_on_question)

        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
        except DuplicateValueError:
            form.form_errors.append(
                f"“{updated_managed_expression.description}” condition based on this question already exists."
            )
        else:
            if "question" in session:
                del session["question"]
            return redirect(return_url)

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=component.form.collection, expression_context_end_point=component
    )

    return render_template(
        "deliver_grant_funding/reports/manage_question_condition_select_condition_type.html",
        component=component,
        grant=component.form.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
        depends_on_question=depends_on_question,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/add-validation",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def add_question_validation(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, question_id=question.id
    )

    ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
    form = (
        ValidationForm(data=add_context_data._prepared_form_data if add_context_data else None)  # type: ignore[union-attr]
        if ValidationForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=question.form.id,
            question_id=question.id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=question.id,
            expression_type=ExpressionType.VALIDATION,
            add_context_data=add_context_data,  # type: ignore[arg-type]
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        expression = form.get_expression(question)

        try:
            interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(f"“{expression.description}” validation already exists on the question.")
        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=question.form.collection, expression_context_end_point=question
    )

    return render_template(
        "deliver_grant_funding/reports/manage_question_validation.html",
        question=question,
        grant=question.form.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
        interpolate=SubmissionHelper.get_interpolator(question.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/validation/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
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

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, question_id=question.id, expression_id=expression_id
    )

    ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, cast("Question", question), expression)
    form = (
        ValidationForm(data=add_context_data._prepared_form_data if add_context_data else None)  # type: ignore[union-attr]
        if ValidationForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=question.form.id,
            question_id=question.id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
            expression_id=expression_id,
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=question.id,
            expression_type=ExpressionType.VALIDATION,
            expression=expression,
            add_context_data=add_context_data,  # type: ignore[arg-type]
        )
        return redirect(request.url)

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
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=question.form.collection, expression_context_end_point=question
    )

    return render_template(
        "deliver_grant_funding/reports/manage_question_validation.html",
        question=question,
        grant=question.form.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
        interpolate=SubmissionHelper.get_interpolator(question.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/report/<uuid:report_id>/submissions/<submission_mode:submission_mode>"
)
@has_deliver_grant_role(RoleEnum.MEMBER)
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
@has_deliver_grant_role(RoleEnum.MEMBER)
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
@has_deliver_grant_role(RoleEnum.MEMBER)
def view_submission(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    helper = SubmissionHelper.load(submission_id)
    return render_template(
        "deliver_grant_funding/reports/view_submission.html",
        grant=helper.grant,
        helper=helper,
        interpolate=SubmissionHelper.get_interpolator(collection=helper.collection, submission_helper=helper),
    )
