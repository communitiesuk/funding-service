from typing import Any
from uuid import UUID

from flask import current_app, flash, redirect, url_for
from flask_admin import AdminIndexView, BaseView, expose

from app.common.data.interfaces.collections import get_collection
from app.common.data.interfaces.exceptions import NotEnoughGrantTeamUsersError
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipients,
    get_grant_recipients,
    get_grant_recipients_count,
)
from app.common.data.interfaces.grants import get_all_grants, get_grant, update_grant
from app.common.data.interfaces.organisations import get_organisation_count, get_organisations, upsert_organisations
from app.common.data.types import GrantStatusEnum
from app.deliver_grant_funding.admin.forms import (
    PlatformAdminBulkCreateGrantRecipientsForm,
    PlatformAdminBulkCreateOrganisationsForm,
    PlatformAdminMakeGrantLiveForm,
    PlatformAdminSelectGrantForReportingLifecycleForm,
    PlatformAdminSelectReportForm,
)
from app.deliver_grant_funding.admin.mixins import FlaskAdminPlatformAdminAccessibleMixin
from app.extensions import auto_commit_after_request


class PlatformAdminBaseView(FlaskAdminPlatformAdminAccessibleMixin, BaseView):
    pass


class PlatformAdminIndexView(FlaskAdminPlatformAdminAccessibleMixin, AdminIndexView):
    pass


class PlatformAdminReportingLifecycleView(PlatformAdminBaseView):
    @expose("/", methods=["GET", "POST"])  # type: ignore[misc]
    def index(self) -> Any:
        form = PlatformAdminSelectGrantForReportingLifecycleForm(grants=get_all_grants())
        if form.validate_on_submit():
            grant = get_grant(form.grant_id.data, with_all_collections=True)
            if len(grant.reports) == 1:
                return redirect(
                    url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=grant.reports[0].id)
                )
            else:
                return redirect(url_for("reporting_lifecycle.select_report", grant_id=grant.id))

        return self.render("deliver_grant_funding/admin/select-grant-for-reporting-lifecycle.html", form=form)

    @expose("/<uuid:grant_id>/select-report", methods=["GET", "POST"])  # type: ignore[misc]
    def select_report(self, grant_id: UUID) -> Any:
        grant = get_grant(grant_id, with_all_collections=True)
        form = PlatformAdminSelectReportForm(collections=grant.reports)
        if form.validate_on_submit():
            return redirect(
                url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=form.collection_id.data)
            )

        return self.render(
            "deliver_grant_funding/admin/select-report-for-reporting-lifecycle.html", form=form, grant=grant
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>")  # type: ignore[misc]
    def tasklist(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id, with_all_collections=True)
        collection = get_collection(collection_id, grant_id=grant_id)
        organisation_count = get_organisation_count()
        grant_recipients_count = get_grant_recipients_count(grant=grant)
        return self.render(
            "deliver_grant_funding/admin/reporting-lifecycle-tasklist.html",
            grant=grant,
            collection=collection,
            organisation_count=organisation_count,
            grant_recipients_count=grant_recipients_count,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/make-live", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def make_live(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        if grant.status == GrantStatusEnum.LIVE:
            flash(f"{grant.name} is already live.")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        form = PlatformAdminMakeGrantLiveForm()
        if form.validate_on_submit():
            try:
                update_grant(grant, status=GrantStatusEnum.LIVE)
                flash(f"{grant.name} is now live.", "success")
                return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))
            except NotEnoughGrantTeamUsersError:
                form.form_errors.append("You must add at least two grant team users before making the grant live")

        return self.render(
            "deliver_grant_funding/admin/confirm-make-grant-live.html", form=form, grant=grant, collection=collection
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-organisations", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_up_organisations(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        form = PlatformAdminBulkCreateOrganisationsForm()
        if form.validate_on_submit():
            organisations = form.get_normalised_organisation_data()
            upsert_organisations(organisations)
            flash(f"Created or updated {len(organisations)} organisations.", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-organisations.html",
            form=form,
            grant=grant,
            collection=collection,
            delta_service_desk_url=current_app.config["DELTA_SERVICE_DESK_URL"],
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-grant-recipients", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_up_grant_recipients(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        organisations = get_organisations(can_manage_grants=False)
        existing_grant_recipients = get_grant_recipients(grant=grant)
        form = PlatformAdminBulkCreateGrantRecipientsForm(
            organisations=organisations, existing_grant_recipients=existing_grant_recipients
        )

        if form.validate_on_submit():
            create_grant_recipients(grant=grant, organisation_ids=form.recipients.data)
            flash(f"Created {len(form.recipients.data)} grant recipients.", "success")  # type: ignore[arg-type]
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-grant-recipients.html",
            grant=grant,
            collection=collection,
            grant_recipients=existing_grant_recipients,
            form=form,
        )
