import csv
from io import BytesIO, StringIO
from typing import Any
from uuid import UUID

import markupsafe
from flask import abort, current_app, flash, redirect, send_file, url_for
from flask_admin import AdminIndexView, BaseView, expose

from app.common.data.interfaces.collections import get_collection, update_collection
from app.common.data.interfaces.exceptions import (
    CollectionChronologyError,
    GrantMustBeLiveError,
    GrantRecipientUsersRequiredError,
    StateTransitionError,
)
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipients,
    get_grant_recipient_data_providers,
    get_grant_recipient_data_providers_count,
    get_grant_recipients,
    get_grant_recipients_count,
    get_grant_recipients_with_outstanding_submissions_for_collection,
)
from app.common.data.interfaces.grants import get_all_grants, get_grant, update_grant
from app.common.data.interfaces.organisations import get_organisation_count, get_organisations, upsert_organisations
from app.common.data.interfaces.user import (
    add_permissions_to_user,
    get_certifiers_by_organisation,
    get_grant_override_certifiers_by_organisation,
    get_user,
    get_user_by_email,
    get_users_with_permission,
    remove_permissions_from_user,
    upsert_user_by_email,
)
from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    GrantRecipientModeEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    ReportAdminEmailTypeEnum,
    RoleEnum,
)
from app.common.filters import format_date
from app.deliver_grant_funding.admin.forms import (
    PlatformAdminAddSingleDataProviderForm,
    PlatformAdminAddTestGrantRecipientUserForm,
    PlatformAdminBulkCreateGrantRecipientsForm,
    PlatformAdminBulkCreateOrganisationsForm,
    PlatformAdminCreateCertifiersForm,
    PlatformAdminCreateGrantOverrideCertifiersForm,
    PlatformAdminCreateGrantRecipientDataProvidersForm,
    PlatformAdminMakeGrantLiveForm,
    PlatformAdminMakeReportLiveForm,
    PlatformAdminMarkAsOnboardingForm,
    PlatformAdminRevokeCertifiersForm,
    PlatformAdminRevokeGrantOverrideCertifiersForm,
    PlatformAdminRevokeGrantRecipientUsersForm,
    PlatformAdminScheduleReportForm,
    PlatformAdminSelectGrantForReportingLifecycleForm,
    PlatformAdminSelectReportForm,
    PlatformAdminSetCollectionDatesForm,
    PlatformAdminSetPrivacyPolicyForm,
)
from app.deliver_grant_funding.admin.mixins import (
    FlaskAdminPlatformMemberAccessibleMixin,
)
from app.extensions import auto_commit_after_request, notification_service


class PlatformAdminIndexView(FlaskAdminPlatformMemberAccessibleMixin, AdminIndexView):
    pass


class PlatformAdminReportingLifecycleView(FlaskAdminPlatformMemberAccessibleMixin, BaseView):
    @expose("/", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/select-report", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>")  # type: ignore[untyped-decorator]
    def tasklist(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id, with_all_collections=True)
        collection = get_collection(collection_id, grant_id=grant_id)
        organisation_count = get_organisation_count()
        certifiers_count = len(get_users_with_permission(RoleEnum.CERTIFIER, grant_id=None))
        grant_recipients_count = get_grant_recipients_count(grant=grant)
        grant_recipient_users_count = get_grant_recipient_data_providers_count(grant=grant)
        grant_override_certifiers_count = len(get_users_with_permission(RoleEnum.CERTIFIER, grant_id=grant_id))

        # Test entity counts
        test_organisations_count = get_organisation_count(mode=OrganisationModeEnum.TEST)
        test_grant_recipients_count = get_grant_recipients_count(grant=grant, mode=GrantRecipientModeEnum.TEST)
        test_users_count = get_grant_recipient_data_providers_count(grant=grant, mode=GrantRecipientModeEnum.TEST)

        return self.render(
            "deliver_grant_funding/admin/reporting-lifecycle-tasklist.html",
            grant=grant,
            collection=collection,
            organisation_count=organisation_count,
            certifiers_count=certifiers_count,
            grant_recipients_count=grant_recipients_count,
            grant_recipient_users_count=grant_recipient_users_count,
            grant_override_certifiers_count=grant_override_certifiers_count,
            test_organisations_count=test_organisations_count,
            test_grant_recipients_count=test_grant_recipients_count,
            test_users_count=test_users_count,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/make-live", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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
            except StateTransitionError:
                form.form_errors.append("Unable to make grant live")

        return self.render(
            "deliver_grant_funding/admin/confirm-make-grant-live.html", form=form, grant=grant, collection=collection
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/mark-as-onboarding", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-privacy-policy", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def set_privacy_policy(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        form = PlatformAdminSetPrivacyPolicyForm(obj=grant)
        if form.validate_on_submit():
            update_grant(grant, privacy_policy_markdown=form.privacy_policy_markdown.data)
            flash(f"Privacy policy updated for {grant.name}.", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-privacy-policy.html",
            form=form,
            grant=grant,
            collection=collection,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-organisations", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-global-certifiers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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
            count = 0
            for org_name, full_name, email_address in certifiers_data:
                org_id = organisation_names_to_ids.get(org_name)
                if org_id:
                    user = upsert_user_by_email(email_address=email_address, name=full_name)
                    add_permissions_to_user(user=user, permissions=[RoleEnum.CERTIFIER], organisation_id=org_id)
                    count += 1

            flash(f"Created or updated {count} certifier(s).", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-global-certifiers.html",
            form=form,
            grant=grant,
            collection=collection,
            certifiers_by_org=certifiers_by_org,
            delta_service_desk_url=current_app.config["DELTA_SERVICE_DESK_URL"],
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/revoke-global-certifiers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/override-grant-certifiers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def override_grant_certifiers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        grant_recipients = get_grant_recipients(grant=grant)

        certifiers_by_org = get_grant_override_certifiers_by_organisation(grant_id=grant_id)

        form = PlatformAdminCreateGrantOverrideCertifiersForm(grant_recipients=grant_recipients)

        if form.validate_on_submit():
            organisation_id = UUID(form.organisation_id.data)
            assert form.full_name.data
            full_name = form.full_name.data
            assert form.email.data
            email_address = form.email.data

            user = upsert_user_by_email(email_address=email_address, name=full_name)
            add_permissions_to_user(
                user=user,
                permissions=[RoleEnum.CERTIFIER],
                organisation_id=organisation_id,
                grant_id=grant_id,
            )

            flash(
                f"Successfully added {full_name} ({email_address}) as a grant-specific certifier.",
                "success",
            )
            return redirect(
                url_for(
                    "reporting_lifecycle.override_grant_certifiers",
                    grant_id=grant.id,
                    collection_id=collection.id,
                )
            )

        return self.render(
            "deliver_grant_funding/admin/override-grant-certifiers.html",
            form=form,
            grant=grant,
            collection=collection,
            certifiers_by_org=certifiers_by_org,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/revoke-grant-override-certifiers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def revoke_grant_override_certifiers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        grant_recipients = get_grant_recipients(grant=grant)

        certifiers_by_org = get_grant_override_certifiers_by_organisation(grant_id=grant_id)

        form = PlatformAdminRevokeGrantOverrideCertifiersForm(grant_recipients=grant_recipients)

        if form.validate_on_submit():
            organisation_id = UUID(form.organisation_id.data)
            assert form.email.data
            email = form.email.data

            user = get_user_by_email(email)
            if not user:
                flash(f"User with email '{email}' does not exist.", "error")
            else:
                certifiers = get_users_with_permission(
                    RoleEnum.CERTIFIER, organisation_id=organisation_id, grant_id=grant_id
                )
                if user not in certifiers:
                    flash(
                        f"User '{user.name}' ({email}) is not a grant-specific certifier "
                        "for the selected organisation.",
                        "error",
                    )
                else:
                    remove_permissions_from_user(
                        user=user,
                        permissions=[RoleEnum.CERTIFIER],
                        organisation_id=organisation_id,
                        grant_id=grant_id,
                    )
                    flash(
                        f"Successfully revoked grant-specific certifier access for {user.name} ({email}).",
                        "success",
                    )
                    return redirect(
                        url_for(
                            "reporting_lifecycle.revoke_grant_override_certifiers",
                            grant_id=grant.id,
                            collection_id=collection.id,
                        )
                    )

        return self.render(
            "deliver_grant_funding/admin/revoke-grant-override-certifiers.html",
            form=form,
            grant=grant,
            collection=collection,
            certifiers_by_org=certifiers_by_org,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-grant-recipients", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/add-individual-data-providers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def add_individual_data_providers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        grant_recipients = get_grant_recipients(grant=grant, with_data_providers=True)
        data_providers_by_grant_recipient = {gr: gr.data_providers for gr in grant_recipients}

        form = PlatformAdminAddSingleDataProviderForm(grant_recipients=grant_recipients)
        if form.validate_on_submit():
            grant_recipient = next(gr for gr in grant_recipients if str(gr.id) == form.grant_recipient.data)
            user = upsert_user_by_email(email_address=form.email_address.data, name=form.full_name.data)
            add_permissions_to_user(
                user,
                permissions=[RoleEnum.DATA_PROVIDER],
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant.id,
            )

            if form.send_notification_email.data:
                notification_service.send_access_report_opened(
                    email_address=user.email,
                    collection=collection,
                    grant_recipient=grant_recipient,
                )
                flash(f"Successfully added {user.name} as a data provider and sent notification email.", "success")
            else:
                flash(f"Successfully added {user.name} as a data provider.", "success")

            return redirect(
                url_for(
                    "reporting_lifecycle.tasklist",
                    grant_id=grant.id,
                    collection_id=collection.id,
                )
            )
        return self.render(
            "deliver_grant_funding/admin/add-individual-data-provider.html",
            form=form,
            grant=grant,
            collection=collection,
            data_providers_by_grant_recipient=data_providers_by_grant_recipient,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/add-bulk-data-providers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def add_bulk_data_providers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        grant_recipients = get_grant_recipients(grant=grant, with_data_providers=True)
        data_providers_by_grant_recipient = {gr: gr.data_providers for gr in grant_recipients}
        form = PlatformAdminCreateGrantRecipientDataProvidersForm(grant_recipients=grant_recipients)
        if form.validate_on_submit():
            grant_recipient_names_to_ids = {gr.organisation.name: gr.organisation.id for gr in grant_recipients}
            users_data = form.get_normalised_users_data()

            for org_name, full_name, email_address in users_data:
                org_id = grant_recipient_names_to_ids[org_name]
                user = upsert_user_by_email(email_address=email_address, name=full_name)
                add_permissions_to_user(
                    user, permissions=[RoleEnum.DATA_PROVIDER], organisation_id=org_id, grant_id=grant.id
                )

            noun = "data provider" if len(users_data) == 1 else "data providers"
            flash(
                f"Successfully set up {len(users_data)} grant recipient {noun}.",
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
            "deliver_grant_funding/admin/add-bulk-data-providers.html",
            form=form,
            grant=grant,
            collection=collection,
            data_providers_by_grant_recipient=data_providers_by_grant_recipient,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-test-organisations", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def set_up_test_organisations(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        form = PlatformAdminBulkCreateOrganisationsForm()
        if form.validate_on_submit():
            organisations = form.get_normalised_organisation_data()
            for org in organisations:
                org.mode = OrganisationModeEnum.TEST
            upsert_organisations(organisations)
            flash(f"Created or updated {len(organisations)} test organisations.", "success")
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-test-organisations.html",
            form=form,
            grant=grant,
            collection=collection,
            delta_service_desk_url=current_app.config["DELTA_SERVICE_DESK_URL"],
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-test-grant-recipients", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def set_up_test_grant_recipients(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)
        organisations = get_organisations(can_manage_grants=False, mode=OrganisationModeEnum.TEST)
        existing_grant_recipients = get_grant_recipients(grant=grant, mode=GrantRecipientModeEnum.TEST)
        form = PlatformAdminBulkCreateGrantRecipientsForm(
            organisations=organisations, existing_grant_recipients=existing_grant_recipients
        )

        if form.validate_on_submit():
            create_grant_recipients(
                grant=grant, organisation_ids=form.recipients.data, mode=GrantRecipientModeEnum.TEST
            )
            flash(f"Created {len(form.recipients.data)} test grant recipients.", "success")  # type: ignore[arg-type]
            return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))

        return self.render(
            "deliver_grant_funding/admin/set-up-test-grant-recipients.html",
            grant=grant,
            collection=collection,
            grant_recipients=existing_grant_recipients,
            form=form,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-up-test-grant-recipient-users", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def set_up_test_grant_recipient_users(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        # Get TEST grant recipients with their current data providers
        grant_recipients = get_grant_recipients(grant=grant, with_data_providers=True, mode=GrantRecipientModeEnum.TEST)

        # Get all Deliver grant funding users who have permissions for this grant
        grant_team_users = grant.grant_team_users

        orgs = get_organisations(can_manage_grants=True)
        if not orgs or len(orgs) > 1:
            raise Exception("Journey requires and only supports one managing organisation (MHCLG)")

        mhclg = orgs[0]
        mhclg_members = list(get_users_with_permission(RoleEnum.MEMBER, organisation_id=mhclg.id, grant_id=None))
        platform_admins = list(get_users_with_permission(RoleEnum.ADMIN, organisation_id=None, grant_id=None))
        mhclg_users = list(set(mhclg_members + platform_admins))

        # Initialize form with dropdown choices
        form = PlatformAdminAddTestGrantRecipientUserForm(
            grant_recipients=grant_recipients,
            grant_team_users=grant_team_users,
            mhclg_users=mhclg_users,
        )

        # Prepare data for template (existing users table)
        data_providers_by_grant_recipient = {gr: gr.data_providers for gr in grant_recipients}

        if form.validate_on_submit():
            # Get selected IDs from form
            grant_recipient_id = UUID(form.grant_recipient.data)

            # Find the selected grant recipient to get its organisation_id
            grant_recipient = next(gr for gr in grant_recipients if gr.id == grant_recipient_id)

            # Find the selected user
            if form.user.data:
                user_id = UUID(form.user.data)
                user = next(u for u in grant_team_users if u.id == user_id)
            else:
                user_id = UUID(form.mhclg_user.data)
                user = next(u for u in mhclg_users if u.id == user_id)

            # Add DATA_PROVIDER and CERTIFIER permissions
            add_permissions_to_user(
                user,
                permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant.id,
            )

            # Flash success message
            flash(
                f"Added {user.name} as a data provider for {grant_recipient.organisation.name}",
                "success",
            )

            # Redirect to same page (clears form and shows updated existing users table)
            return redirect(
                url_for(
                    ".set_up_test_grant_recipient_users",
                    grant_id=grant_id,
                    collection_id=collection_id,
                )
            )

        return self.render(
            "deliver_grant_funding/admin/set-up-test-grant-recipient-users.html",
            grant=grant,
            collection=collection,
            form=form,
            data_providers_by_grant_recipient=data_providers_by_grant_recipient,
            grant_recipients=grant_recipients,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/revoke-grant-recipient-data-providers", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def revoke_grant_recipient_data_providers(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id)

        grant_recipients_data_providers = get_grant_recipient_data_providers(grant)
        form = PlatformAdminRevokeGrantRecipientUsersForm(
            grant_recipients_data_providers=grant_recipients_data_providers
        )

        if form.validate_on_submit():
            revoked_count = 0
            assert form.grant_recipients_data_providers.data
            for user_role_id in form.grant_recipients_data_providers.data:
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
                    "reporting_lifecycle.add_bulk_data_providers",
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/set-dates", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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

    @expose("/<uuid:grant_id>/<uuid:collection_id>/schedule-report", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
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
            except (GrantMustBeLiveError, GrantRecipientUsersRequiredError, CollectionChronologyError) as e:
                form.form_errors.append(str(e))

        return self.render(
            "deliver_grant_funding/admin/confirm-schedule-report.html",
            form=form,
            grant=grant,
            collection=collection,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/make-report-live", methods=["GET", "POST"])  # type: ignore[untyped-decorator]
    @auto_commit_after_request
    def make_report_live(self, grant_id: UUID, collection_id: UUID) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

        form = PlatformAdminMakeReportLiveForm()
        if form.validate_on_submit():
            try:
                update_collection(collection, status=CollectionStatusEnum.OPEN)
                flash(
                    (
                        f"{markupsafe.escape(collection.name)} is now live and grant recipients can start making "
                        f"submissions. "
                        "<strong>You must now send emails to grant recipient users to let them know the report is "
                        "open for submissions.</strong>"
                    ),
                    "success",
                )
                return redirect(url_for("reporting_lifecycle.tasklist", grant_id=grant.id, collection_id=collection.id))
            except StateTransitionError as e:
                form.form_errors.append(
                    f"{collection.name} can only be made live from the 'scheduled' state; "
                    f"it is currently {e.from_state}",
                )
            except (GrantMustBeLiveError, GrantRecipientUsersRequiredError, CollectionChronologyError) as e:
                form.form_errors.append(str(e))

        return self.render(
            "deliver_grant_funding/admin/confirm-make-report-live.html",
            form=form,
            grant=grant,
            collection=collection,
        )

    @expose("/<uuid:grant_id>/<uuid:collection_id>/send-emails-to-data-providers/<email_type>", methods=["GET"])  # type: ignore[untyped-decorator]
    def send_emails_to_recipients(
        self, grant_id: UUID, collection_id: UUID, email_type: ReportAdminEmailTypeEnum
    ) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

        notify_service_id = current_app.config["GOVUK_NOTIFY_SERVICE_ID"]
        match email_type:
            case ReportAdminEmailTypeEnum.REPORT_OPEN_NOTIFICATION:
                notify_template_id = current_app.config["GOVUK_NOTIFY_GRANT_RECIPIENT_REPORT_NOTIFICATION_TEMPLATE_ID"]
            case ReportAdminEmailTypeEnum.DEADLINE_REMINDER:
                if not collection.status == CollectionStatusEnum.OPEN:
                    return abort(404)
                notify_template_id = current_app.config[
                    "GOVUK_NOTIFY_GRANT_RECIPIENT_REPORT_DEADLINE_REMINDER_TEMPLATE_ID"
                ]
            case _:
                return abort(404)

        return self.render(
            "deliver_grant_funding/admin/send-emails-to-data-providers.html",
            grant=grant,
            collection=collection,
            notify_template_url=f"https://www.notifications.service.gov.uk/services/{notify_service_id}/send/{notify_template_id}/csv",
            email_type=email_type,
        )

    @expose(  # type: ignore[untyped-decorator]
        "/<uuid:grant_id>/<uuid:collection_id>/send-emails-to-data-providers/download-csv/<email_type>", methods=["GET"]
    )
    def download_data_providers_csv(
        self, grant_id: UUID, collection_id: UUID, email_type: ReportAdminEmailTypeEnum
    ) -> Any:
        grant = get_grant(grant_id)
        collection = get_collection(collection_id, grant_id=grant_id, type_=CollectionType.MONITORING_REPORT)

        assert collection.submission_period_end_date

        csv_output = StringIO()
        csv_writer = csv.DictWriter(
            csv_output,
            fieldnames=[
                "email_address",
                "grant_name",
                "organisation_name",
                "report_name",
                "report_deadline",
                "grant_report_url",
                "is_test_data",
                "requires_certification",
            ],
        )
        csv_writer.writeheader()
        email_recipients = set()

        match email_type:
            case ReportAdminEmailTypeEnum.REPORT_OPEN_NOTIFICATION:
                grant_recipients = get_grant_recipients(grant=grant, with_data_providers=True)
                email_recipients = {
                    (data_provider, grant_recipient)
                    for grant_recipient in grant_recipients
                    for data_provider in grant_recipient.data_providers
                }
            case ReportAdminEmailTypeEnum.DEADLINE_REMINDER:
                grant_recipients = get_grant_recipients_with_outstanding_submissions_for_collection(
                    grant, collection_id=collection.id, with_data_providers=True, with_certifiers=True
                )
                email_recipients = {
                    (recipient_user, grant_recipient)
                    for grant_recipient in grant_recipients
                    for recipient_user in grant_recipient.data_providers + list(grant_recipient.certifiers)
                }
            case _:
                return abort(404)
        for email_recipient, grant_recipient in sorted(email_recipients, key=lambda u: u[0].email):
            report_name = collection.name
            report_deadline = format_date(collection.submission_period_end_date)

            grant_report_url = url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
                _external=True,
            )

            csv_writer.writerow(
                {
                    "email_address": email_recipient.email,
                    "grant_name": grant.name,
                    "organisation_name": grant_recipient.organisation.name,
                    "report_name": report_name,
                    "report_deadline": report_deadline,
                    "grant_report_url": grant_report_url,
                    "is_test_data": "yes" if grant_recipient.mode == GrantRecipientModeEnum.TEST else "no",
                    "requires_certification": "yes" if collection.requires_certification else "no",
                }
            )

        csv_bytes = BytesIO(csv_output.getvalue().encode("utf-8"))
        csv_bytes.seek(0)

        filename = (
            f"grant-recipients-{grant.name.lower().replace(' ', '-')}-{collection.name.lower().replace(' ', '-')}.csv"
        )

        return send_file(
            csv_bytes,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )
