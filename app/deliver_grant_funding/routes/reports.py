from uuid import UUID

from flask import abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import has_grant_role
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_collection,
    create_form,
    delete_collection,
    get_collection,
    update_collection,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grants import get_grant
from app.common.data.types import CollectionType, RoleEnum
from app.common.forms import GenericConfirmDeletionForm
from app.deliver_grant_funding.forms import AddTaskForm, SetUpReportForm
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/reports", methods=["GET"])
@has_grant_role(RoleEnum.MEMBER)
def list_reports(grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)
    return render_template("deliver_grant_funding/reports/list_reports.html", grant=grant)


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


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/report/<uuid:report_id>/manage", methods=["GET", "POST"])
@has_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def manage_report(grant_id: UUID, report_id: UUID) -> ResponseReturnValue:
    # NOTE: this fetches the _latest version_ of the collection with this ID
    report = get_collection(report_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

    delete_form = GenericConfirmDeletionForm() if "delete" in request.args and not report.live_submissions else None
    if delete_form and delete_form.validate_on_submit():
        if report.live_submissions:
            abort(400)

        delete_collection(report)

        return redirect(url_for("deliver_grant_funding.list_reports", grant_id=report.grant_id))

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
        "deliver_grant_funding/reports/manage.html",
        grant=report.grant,
        report=report,
        delete_form=delete_form,
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
