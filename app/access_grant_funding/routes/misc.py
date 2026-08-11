from functools import partial
from uuid import UUID

from flask import abort, current_app, flash, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.forms import AddGrantTeamMemberForm, EligibleOrganisationSelectionForm
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import (
    access_grant_funding_login_required,
    can_invite_access_grant_team_member,
    collection_is_open_for_sign_up,
    has_access_grant_recipient_role,
    has_access_grant_role,
    has_feature_flag_enabled,
    is_access_org_member,
    is_signing_up,
)
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipient,
    get_grant_recipient,
    get_grant_recipient_or_none,
)
from app.common.data.interfaces.grants import get_grant, get_grant_by_slug
from app.common.data.interfaces.organisations import get_matched_organisations, get_organisation
from app.common.data.types import (
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    OrganisationModeEnum,
    RoleEnum,
)
from app.common.forms import GenericSubmitForm
from app.common.helpers.feature_flags import FeatureFlags
from app.common.markdown import convert_text_to_govuk_markup
from app.extensions import auto_commit_after_request
from app.types import FlashMessageType


@access_grant_funding_blueprint.route("/", methods=["GET"])
@access_grant_funding_login_required
def index() -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    grant_recipients = user.get_grant_recipients()

    if not grant_recipients:
        current_app.logger.error("Authorised user has no access to organisation or grants")
        return abort(403)

    unique_org_ids = {grant_recipient.organisation_id for grant_recipient in grant_recipients}

    if len(unique_org_ids) == 1:
        unique_grant_ids = {grant_recipient.grant_id for grant_recipient in grant_recipients}
        if len(unique_grant_ids) == 1:
            grant_recipient = grant_recipients[0]
            return redirect(
                url_for(
                    "access_grant_funding.list_collections",
                    organisation_id=grant_recipient.organisation.id,
                    grant_id=grant_recipient.grant.id,
                )
            )
        else:
            return redirect(
                url_for("access_grant_funding.list_grants", organisation_id=grant_recipients[0].organisation.id)
            )
    else:
        return redirect(url_for("access_grant_funding.list_organisations"))


@access_grant_funding_blueprint.route("/organisation/<uuid:organisation_id>/grants", methods=["GET"])
@is_access_org_member
def list_grants(organisation_id: UUID) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    organisation = get_organisation(organisation_id=organisation_id)
    grants = [
        grant_recipient.grant for grant_recipient in user.get_grant_recipients(limit_to_organisation_id=organisation_id)
    ]
    grants.sort(key=lambda grant: grant.name)
    return render_template("access_grant_funding/grant_list.html", grants=grants, organisation=organisation)


@access_grant_funding_blueprint.route("/organisations", methods=["GET"])
@has_access_grant_recipient_role
def list_organisations() -> ResponseReturnValue:
    user = interfaces.user.get_current_user()
    grant_recipients = user.get_grant_recipients()

    unique_orgs = {gr.organisation for gr in grant_recipients}
    sorted_orgs = sorted(list(unique_orgs), key=lambda org: org.name)

    if len(sorted_orgs) == 1:
        return redirect(url_for("access_grant_funding.list_grants", organisation_id=sorted_orgs[0].id))

    return render_template("access_grant_funding/organisation_list.html", organisations=sorted_orgs)


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/users", methods=["GET"]
)
@has_access_grant_role(RoleEnum.MEMBER)
def list_grant_team(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    organisation = get_organisation(organisation_id=organisation_id)
    grant_recipient = get_grant_recipient(grant_id, organisation_id)

    data_providers = grant_recipient.data_providers
    certifiers = list(grant_recipient.certifiers)
    users = sorted(set(data_providers + certifiers), key=lambda user: (0 if user in data_providers else 1, user.name))

    return render_template(
        "access_grant_funding/grant_team.html",
        users=users,
        organisation=organisation,
        grant_recipient=grant_recipient,
        service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
    )


@access_grant_funding_blueprint.route(
    "/organisation/<uuid:organisation_id>/grants/<uuid:grant_id>/users/add", methods=["GET", "POST"]
)
@can_invite_access_grant_team_member
@has_feature_flag_enabled(FeatureFlags.ACCESS_GRANT_FUNDING_USER_MANAGEMENT)
@auto_commit_after_request
def add_grant_team_member(organisation_id: UUID, grant_id: UUID) -> ResponseReturnValue:
    organisation = get_organisation(organisation_id=organisation_id)
    grant_recipient = get_grant_recipient(grant_id, organisation_id)

    form = AddGrantTeamMemberForm()
    if form.validate_on_submit():
        assert form.email_address.data
        user_to_add = interfaces.user.get_user_by_email(form.email_address.data)
        if user_to_add is None:
            # TODO: https://mhclgdigital.atlassian.net/browse/FSPT-1586
            return abort(500)

        # Covers existing data providers and certifiers; certifiers must not be given edit and submit permissions
        if AuthorisationHelper.is_access_grant_member(grant_recipient, user_to_add):
            # TODO: https://mhclgdigital.atlassian.net/browse/FSPT-1588
            return abort(500)

        interfaces.user.add_permissions_to_user(
            user=user_to_add,
            permissions=[RoleEnum.DATA_PROVIDER],
            organisation_id=organisation.id,
            grant_id=grant_recipient.grant_id,
        )
        flash(
            {"user_name": user_to_add.name},  # ty: ignore[invalid-argument-type]
            FlashMessageType.ACCESS_TEAM_MEMBER_ADDED,
        )
        return redirect(
            url_for("access_grant_funding.list_grant_team", organisation_id=organisation.id, grant_id=grant_id)
        )

    return render_template(
        "access_grant_funding/add_grant_team_member.html",
        form=form,
        organisation=organisation,
        grant_recipient=grant_recipient,
        service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
    )


@access_grant_funding_blueprint.route("/accessibility-statement")
def accessibility_statement() -> ResponseReturnValue:
    return render_template("access_grant_funding/accessibility-statement.html")


@access_grant_funding_blueprint.route("/cookies")
def cookies() -> ResponseReturnValue:
    return render_template("access_grant_funding/cookies.html")


@access_grant_funding_blueprint.route("/privacy-policy")
@access_grant_funding_blueprint.route("/privacy-policy/<uuid:grant_id>")
def privacy_policy(grant_id: UUID | None = None) -> ResponseReturnValue:
    grant = get_grant(grant_id) if grant_id else None
    privacy_policy_renderer = partial(
        convert_text_to_govuk_markup,
        heading_level_start=3,
        heading_level_end=4,
        heading_level_classes=("govuk-heading-m", "govuk-heading-s"),
    )
    return render_template(
        "access_grant_funding/privacy-policy.html", grant=grant, privacy_policy_renderer=privacy_policy_renderer
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/sign-up-router", methods=["GET"]
)
@is_signing_up
def public_sign_up_router(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    # TODO: once the eligibility section exists, check the user's session/progress against it
    # (Collection.eligibility_section.status) and route to "you are eligible"/"you are not
    # eligible"/the next unanswered eligibility question as appropriate. For now this always
    # routes straight to `eligible_to_apply`.
    return redirect(
        url_for(
            "access_grant_funding.eligible_to_apply",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
    )


@access_grant_funding_blueprint.route("/grant/<string:grant_slug>/<string:collection_slug>", methods=["GET", "POST"])
@collection_is_open_for_sign_up
def public_sign_up_start_page(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    form = GenericSubmitForm()
    if form.validate_on_submit():
        # Deliver users testing this journey skip the magic link journey
        user = interfaces.user.get_current_user()
        if user.is_authenticated and AuthorisationHelper.is_deliver_user_testing_access(user):
            return redirect(
                url_for(
                    "access_grant_funding.public_sign_up_router",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                )
            )

        session["signing_up_for_collection_id"] = collection.id
        return redirect(
            url_for(
                "auth.collection_request_a_link_to_public_sign_up",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

    return render_template(
        "access_grant_funding/public_sign_up_start_page.html",
        grant=grant,
        collection=collection,
        form=form,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/eligible-to-apply", methods=["GET", "POST"]
)
@is_signing_up
@auto_commit_after_request
def eligible_to_apply(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    user = interfaces.user.get_current_user()
    email_domain = user.email_domain
    is_deliver_testing = AuthorisationHelper.is_deliver_user_testing_access(user)

    organisation_mode = OrganisationModeEnum.TEST if is_deliver_testing else OrganisationModeEnum.LIVE
    matched_orgs = get_matched_organisations(user, email_domain, mode=organisation_mode)

    # No organisations matched, show message and link to sign up a new organisation
    if len(matched_orgs.all) == 0:
        return render_template(
            "access_grant_funding/eligible_to_apply.html",
            grant=grant,
            collection=collection,
            service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
        )

    # One organisation matched case
    if len(matched_orgs.all) == 1:
        organisations = None
        organisation = matched_orgs.all[0]
        form = GenericSubmitForm()
    # Multiple organisations matched case, show radio buttons to select one
    elif len(matched_orgs.all) > 1:
        organisations = matched_orgs
        organisation = matched_orgs.all[0]  # default to first
        form = EligibleOrganisationSelectionForm(
            matched_orgs.role_matched_orgs,
            matched_orgs.domain_matched_orgs,
            email_domain,
        )

    if form.validate_on_submit():
        # For multiple organisation match case, get the selected organisation
        if isinstance(form, EligibleOrganisationSelectionForm):
            selected = form.organisation.data
            # If user selected to create a new organisation
            if selected == form.SIGN_UP_NEW_ORGANISATION_VALUE:
                # TODO: wire up to the create-account/org flow once it exists
                return redirect(
                    url_for(
                        "access_grant_funding.eligible_to_apply",
                        grant_slug=grant_slug,
                        collection_slug=collection_slug,
                    )
                )
            organisation = get_organisation(UUID(selected))

        session.pop("signing_up_for_collection_id", None)

        grant_recipient_mode = GrantRecipientModeEnum.TEST if is_deliver_testing else GrantRecipientModeEnum.LIVE
        grant_recipient = get_grant_recipient_or_none(grant.id, organisation.id)

        # No grant recipient exists, create one
        if grant_recipient is None:
            create_grant_recipient(
                grant=grant,
                organisation=organisation,
                status=GrantRecipientStatusEnum.APPLYING,
                mode=grant_recipient_mode,
            )

            interfaces.user.add_permissions_to_user(
                user=user,
                permissions=[RoleEnum.DATA_PROVIDER],
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        # A grant recipient exists, and user does not have access to it
        elif not AuthorisationHelper.has_access_grant_role(grant_recipient, RoleEnum.MEMBER, user):
            # TODO: Update when adding the Org is already applying page
            return abort(403, "You do not have access to this grant")

        flash("Sign in complete. You can start your application.", FlashMessageType.PUBLIC_SIGN_UP_SUCCESS)

        return redirect(
            url_for(
                "access_grant_funding.list_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

    return render_template(
        "access_grant_funding/eligible_to_apply.html",
        grant=grant,
        collection=collection,
        organisation=organisation,
        organisations=organisations,
        form=form,
        service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
    )
