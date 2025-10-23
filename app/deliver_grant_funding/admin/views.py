from typing import Any
from uuid import UUID

from flask import flash, redirect, url_for
from flask_admin import AdminIndexView, BaseView, expose

from app.common.data.interfaces.exceptions import NotEnoughGrantTeamUsersError
from app.common.data.interfaces.grants import get_all_grants, get_grant, update_grant
from app.common.data.types import GrantStatusEnum
from app.deliver_grant_funding.admin.forms import (
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
        return self.render("deliver_grant_funding/admin/reporting-lifecycle-tasklist.html", grant=grant)

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
