from functools import partial
from uuid import UUID

from flask import abort, current_app, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.decorators import (
    access_grant_funding_login_required,
    has_access_grant_recipient_role,
    has_access_grant_role,
    is_access_org_member,
    validate_public_sign_off,
)
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.interfaces.grants import get_grant, get_grant_by_slug
from app.common.data.interfaces.organisations import get_organisation, get_organisations
from app.common.data.types import RoleEnum
from app.common.markdown import convert_text_to_govuk_markup


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


@access_grant_funding_blueprint.route("/grant/<string:grant_slug>/<string:collection_slug>")
@validate_public_sign_off
def public_sign_off_start_page(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    return render_template(
        "access_grant_funding/public_sign_off_start_page.html",
        grant=grant,
        collection=collection,
    )


@access_grant_funding_blueprint.route("/grant/<string:grant_slug>/<string:collection_slug>/eligible")
@validate_public_sign_off
@access_grant_funding_login_required
def eligible_to_apply(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    user = interfaces.user.get_current_user()
    email_domain = user.email.split("@")[-1]
    organisations = get_organisations(domain=email_domain)

    if len(organisations) == 0:
        return abort(400, "No organisation found for this email domain")
    if len(organisations) > 1:
        return abort(400, "Multiple organisations found for this email domain")

    organisation = organisations[0]

    return render_template(
        "access_grant_funding/eligible_to_apply.html",
        grant=grant,
        collection=collection,
        organisation=organisation,
        service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
    )
