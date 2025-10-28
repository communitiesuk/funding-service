from typing import Any
from uuid import UUID

from flask import flash, redirect, url_for
from flask_admin import AdminIndexView, BaseView, expose

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
            grant = get_grant(form.grant_id.data)
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id))

        return self.render("deliver_grant_funding/admin/select-grant-for-reporting-lifecycle.html", form=form)

    @expose("/<uuid:grant_id>")  # type: ignore[misc]
    def tasklist(self, grant_id: UUID) -> Any:
        grant = get_grant(grant_id)
        organisation_count = get_organisation_count()
        grant_recipients_count = get_grant_recipients_count(grant=grant)
        return self.render(
            "deliver_grant_funding/admin/reporting-lifecycle-tasklist.html",
            grant=grant,
            organisation_count=organisation_count,
            grant_recipients_count=grant_recipients_count,
        )

    @expose("/<uuid:grant_id>/make-live", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def make_live(self, grant_id: UUID) -> Any:
        grant = get_grant(grant_id)

        if grant.status == GrantStatusEnum.LIVE:
            flash(f"{grant.name} is already live.")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id))

        form = PlatformAdminMakeGrantLiveForm()
        if form.validate_on_submit():
            try:
                update_grant(grant, status=GrantStatusEnum.LIVE)
                flash(f"{grant.name} is now live.", "success")
                return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id))
            except NotEnoughGrantTeamUsersError:
                form.form_errors.append("You must add at least two grant team users before making the grant live")

        return self.render("deliver_grant_funding/admin/confirm-make-grant-live.html", form=form, grant=grant)

    @expose("/<uuid:grant_id>/set-up-organisations", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_up_organisations(self, grant_id: UUID) -> Any:
        grant = get_grant(grant_id)
        form = PlatformAdminBulkCreateOrganisationsForm()
        if form.validate_on_submit():
            organisations = form.get_normalised_organisation_data()
            upsert_organisations(organisations)
            flash(f"Created or updated {len(organisations)} organisations.", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id))

        return self.render("deliver_grant_funding/admin/set-up-organisations.html", form=form, grant=grant)

    @expose("/<uuid:grant_id>/set-up-grant-recipients", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_up_grant_recipients(self, grant_id: UUID) -> Any:
        grant = get_grant(grant_id)
        organisations = get_organisations(can_manage_grants=False)
        existing_grant_recipients = get_grant_recipients(grant=grant)
        form = PlatformAdminBulkCreateGrantRecipientsForm(
            organisations=organisations, existing_grant_recipients=existing_grant_recipients
        )

        if form.validate_on_submit():
            create_grant_recipients(grant=grant, organisation_ids=form.recipients.data)
            flash(f"Created {len(form.recipients.data)} grant recipients.", "success")  # type: ignore[arg-type]
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-grant-recipients.html",
            grant=grant,
            grant_recipients=existing_grant_recipients,
            form=form,
        )
