from typing import Any
from uuid import UUID

from flask import current_app, flash, redirect, url_for
from flask_admin import AdminIndexView, BaseView, expose

from app.common.data.interfaces.collections import get_collection, update_collection
from app.common.data.interfaces.exceptions import (
    CollectionChronologyError,
    GrantMustBeLiveError,
    GrantRecipientUsersRequiredError,
    NotEnoughGrantTeamUsersError,
    StateTransitionError,
)
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipients,
    get_grant_recipient_data_provider_roles,
    get_grant_recipient_data_providers_by_organisation,
    get_grant_recipient_data_providers_count,
    get_grant_recipients,
    get_grant_recipients_count,
)
from app.common.data.interfaces.grants import get_all_grants, get_grant, update_grant
from app.common.data.interfaces.organisations import get_organisation_count, get_organisations, upsert_organisations
from app.common.data.interfaces.user import (
    add_permissions_to_user,
    get_certifiers_by_organisation,
    get_user,
    get_user_by_email,
    get_users_with_permission,
    remove_permissions_from_user,
    upsert_user_by_email,
)
from app.common.data.types import CollectionStatusEnum, CollectionType, GrantStatusEnum, RoleEnum
from app.deliver_grant_funding.admin.forms import (
    PlatformAdminBulkCreateGrantRecipientsForm,
    PlatformAdminBulkCreateOrganisationsForm,
    PlatformAdminCreateCertifiersForm,
    PlatformAdminCreateGrantRecipientUserForm,
    PlatformAdminMakeGrantLiveForm,
    PlatformAdminMakeReportLiveForm,
    PlatformAdminMarkAsOnboardingForm,
    PlatformAdminRevokeCertifiersForm,
    PlatformAdminRevokeGrantRecipientUsersForm,
    PlatformAdminScheduleReportForm,
    PlatformAdminSelectGrantForReportingLifecycleForm,
    PlatformAdminSelectReportForm,
    PlatformAdminSetCollectionDatesForm,
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
        certifiers_count = len(get_users_with_permission(RoleEnum.CERTIFIER, grant_id=None))
        grant_recipients_count = get_grant_recipients_count(grant=grant)
        grant_recipient_users_count = get_grant_recipient_data_providers_count(grant=grant)
        return self.render(
            "deliver_grant_funding/admin/reporting-lifecycle-tasklist.html",
            grant=grant,
            collection=collection,
            organisation_count=organisation_count,
            certifiers_count=certifiers_count,
            grant_recipients_count=grant_recipients_count,
            grant_recipient_users_count=grant_recipient_users_count,
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/mark-as-onboarding", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def mark_as_onboarding(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        if grant.status in [GrantStatusEnum.ONBOARDING, GrantStatusEnum.LIVE]:
            flash(f"{grant.name} is already marked as onboarding.")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        form = PlatformAdminMarkAsOnboardingForm()
        if form.validate_on_submit():
            update_grant(grant, status=GrantStatusEnum.ONBOARDING)
            flash(f"{grant.name} is now marked as onboarding.", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/confirm-make-grant-active-onboarding.html",
            form=form,
            grant=grant,
            collection=collection,
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-global-certifiers", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_up_global_certifiers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        organisations = get_organisations(can_manage_grants=False)
        certifiers_by_org = get_certifiers_by_organisation()

        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        if form.validate_on_submit():
            certifiers_data = form.get_normalised_certifiers_data()

            organisation_names_to_ids = {organisation.name: organisation.id for organisation in organisations}
            for org_name, full_name, email_address in certifiers_data:
                org_id = organisation_names_to_ids[org_name]
                user = upsert_user_by_email(email_address=email_address, name=full_name)
                add_permissions_to_user(user=user, permissions=[RoleEnum.CERTIFIER], organisation_id=org_id)

            flash(f"Created or updated {len(certifiers_data)} certifier(s).", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-global-certifiers.html",
            form=form,
            grant=grant,
            collection=collection,
            certifiers_by_org=certifiers_by_org,
            delta_service_desk_url=current_app.config["DELTA_SERVICE_DESK_URL"],
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/revoke-global-certifiers", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def revoke_global_certifiers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        organisations = get_organisations()
        certifiers_by_org = get_certifiers_by_organisation()
        form = PlatformAdminRevokeCertifiersForm(organisations=organisations)

        if form.validate_on_submit():
            organisation_id = UUID(form.organisation_id.data)
            assert form.email.data
            email = form.email.data

            user = get_user_by_email(email)
            if not user:
                flash(f"User with email '{email}' does not exist.", "error")
            else:
                certifiers = get_users_with_permission(
                    RoleEnum.CERTIFIER, organisation_id=organisation_id, grant_id=None
                )
                if user not in certifiers:
                    flash(
                        f"User '{user.name}' ({email}) is not a global certifier for the selected organisation.",
                        "error",
                    )
                else:
                    remove_permissions_from_user(
                        user=user,
                        permissions=[RoleEnum.CERTIFIER],
                        organisation_id=organisation_id,
                        grant_id=None,
                    )
                    flash(
                        f"Successfully revoked certifier access for {user.name} ({email}).",
                        "success",
                    )
                    return redirect(
                        url_for(
                            "reporting_lifecycle.revoke_global_certifiers",
                            grant_id=grant.id,
                            collection_id=collection.id,
                        )
                    )

        return self.render(
            "deliver_grant_funding/admin/revoke-global-certifiers.html",
            form=form,
            grant=grant,
            collection=collection,
            certifiers_by_org=certifiers_by_org,
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-grant-recipient-data-providers", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_up_grant_recipient_data_providers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        grant_recipients = get_grant_recipients(grant=grant)
        form = PlatformAdminCreateGrantRecipientUserForm(grant_recipients=grant_recipients)

        grant_recipient_users_by_org = get_grant_recipient_data_providers_by_organisation(grant)

        if form.validate_on_submit():
            grant_recipient_names_to_ids = {gr.organisation.name: gr.organisation.id for gr in grant_recipients}
            users_data = form.get_normalised_users_data()

            # Validate all organisation names first before creating any users
            invalid_orgs = []
            for org_name, _, _ in users_data:
                if org_name not in grant_recipient_names_to_ids:
                    invalid_orgs.append(org_name)

            if invalid_orgs:
                unique_invalid_orgs = sorted(set(invalid_orgs))
                for org_name in unique_invalid_orgs:
                    flash(f"Organisation '{org_name}' is not a grant recipient for this grant.", "error")
                return self.render(
                    "deliver_grant_funding/admin/set-up-grant-recipient-data-providers.html",
                    form=form,
                    grant=grant,
                    collection=collection,
                    grant_recipient_users_by_org=grant_recipient_users_by_org,
                )

            # All organisations are valid, create all users
            for org_name, full_name, email_address in users_data:
                org_id = grant_recipient_names_to_ids[org_name]
                user = upsert_user_by_email(email_address=email_address, name=full_name)
                add_permissions_to_user(
                    user, permissions=[RoleEnum.DATA_PROVIDER], organisation_id=org_id, grant_id=grant.id
                )

            data_provider = "data provider" if len(users_data) == 1 else "data providers"
            flash(
                f"Successfully set up {len(users_data)} grant recipient {data_provider}.",
                "success",
            )

            return redirect(
                url_for(
                    "reporting_lifecycle.tasklist",
                    grant_id=grant.id,
                    collection_id=collection.id,
                )
            )

        return self.render(
            "deliver_grant_funding/admin/set-up-grant-recipient-data-providers.html",
            form=form,
            grant=grant,
            collection=collection,
            grant_recipient_users_by_org=grant_recipient_users_by_org,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/revoke-grant-recipient-data-providers", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def revoke_grant_recipient_data_providers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        user_roles = get_grant_recipient_data_provider_roles(grant)
        form = PlatformAdminRevokeGrantRecipientUsersForm(user_roles=user_roles)

        if form.validate_on_submit():
            revoked_count = 0
            assert form.user_roles.data
            for user_role_id in form.user_roles.data:
                user_id_str, org_id_str = user_role_id.split("|")
                user_id = UUID(user_id_str)
                org_id = UUID(org_id_str)

                if (
                    remove_permissions_from_user(
                        get_user(user_id),
                        permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
                        organisation_id=org_id,
                        grant_id=grant.id,
                    )
                    is None
                ):
                    revoked_count += 1

            if revoked_count > 0:
                data_provider = "data provider" if revoked_count == 1 else "data providers"
                flash(
                    f"Successfully revoked access for {revoked_count} {data_provider}.",
                    "success",
                )
            else:
                flash("No data providers were revoked.", "error")

            return redirect(
                url_for(
                    "reporting_lifecycle.set_up_grant_recipient_data_providers",
                    grant_id=grant.id,
                    collection_id=collection.id,
                )
            )

        return self.render(
            "deliver_grant_funding/admin/revoke-grant-recipient-data-providers.html",
            form=form,
            grant=grant,
            collection=collection,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-dates", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def set_collection_dates(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

        if collection.status != CollectionStatusEnum.DRAFT:
            flash(
                f"You cannot set dates for {collection.name} because it is not in draft status.",
                "error",
            )
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        form = PlatformAdminSetCollectionDatesForm(obj=collection)

        if form.validate_on_submit():
            update_collection(
                collection,
                reporting_period_start_date=form.reporting_period_start_date.data,
                reporting_period_end_date=form.reporting_period_end_date.data,
                submission_period_start_date=form.submission_period_start_date.data,
                submission_period_end_date=form.submission_period_end_date.data,
            )
            flash(f"Updated dates for {collection.name}.", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-collection-dates.html",
            form=form,
            grant=grant,
            collection=collection,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/schedule-report", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def schedule_report(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

        form = PlatformAdminScheduleReportForm()
        if form.validate_on_submit():
            try:
                update_collection(collection, status=CollectionStatusEnum.SCHEDULED)
                flash(
                    f"{collection.name} is now locked and form designers cannot make any more changes.",
                    "success",
                )
                return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))
            except StateTransitionError as e:
                form.form_errors.append(
                    f"{collection.name} can only be scheduled from the 'draft' state; it is currently {e.from_state}",
                )
            except GrantMustBeLiveError as e:
                form.form_errors.append(str(e))
            except GrantRecipientUsersRequiredError as e:
                form.form_errors.append(str(e))
            except CollectionChronologyError as e:
                form.form_errors.append(str(e))

        return self.render(
            "deliver_grant_funding/admin/confirm-schedule-report.html",
            form=form,
            grant=grant,
            collection=collection,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/make-report-live", methods=["GET", "POST"])  # type: ignore[misc]
    @auto_commit_after_request
    def make_report_live(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

        form = PlatformAdminMakeReportLiveForm()
        if form.validate_on_submit():
            try:
                update_collection(collection, status=CollectionStatusEnum.OPEN)
                flash(
                    f"{collection.name} is now live and grant recipients can start making submissions.",
                    "success",
                )
                return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))
            except StateTransitionError as e:
                form.form_errors.append(
                    f"{collection.name} can only be made live from the 'scheduled' state; "
                    f"it is currently {e.from_state}",
                )
            except GrantMustBeLiveError as e:
                form.form_errors.append(str(e))
            except GrantRecipientUsersRequiredError as e:
                form.form_errors.append(str(e))
            except CollectionChronologyError as e:
                form.form_errors.append(str(e))

        return self.render(
            "deliver_grant_funding/admin/confirm-make-report-live.html",
            form=form,
            grant=grant,
            collection=collection,
        )
