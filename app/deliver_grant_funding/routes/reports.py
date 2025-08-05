import uuid
from uuid import UUID

from flask import abort, current_app, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_grant_role
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_collection,
    create_form,
    delete_collection,
    get_collection,
    get_form_by_id,
    update_collection,
    update_form,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import CollectionType, RoleEnum
from app.common.forms import GenericConfirmDeletionForm
from app.deliver_grant_funding.forms import AddTaskForm, SetUpReportForm
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request


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
            abort(400)

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


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/report/<uuid:report_id>", methods=["GET"])
@has_grant_role(RoleEnum.MEMBER)
def list_report_tasks(grant_id: UUID, report_id: UUID) -> ResponseReturnValue:
    report = get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT, with_full_schema=True)

    if report.has_non_default_sections:
        raise RuntimeError(f"Report {report_id} has non-default sections - `add_task` needs updating to handle this.")

    return render_template("deliver_grant_funding/reports/list_report_tasks.html", grant=report.grant, report=report)


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
                    "deliver_grant_funding.list_report_tasks",
                    grant_id=grant_id,
                    report_id=db_form.section.collection_id,
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
