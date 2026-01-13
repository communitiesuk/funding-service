from uuid import UUID

from flask import redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from wtforms import Field

from app.common.auth.decorators import has_deliver_grant_role, is_platform_admin
from app.common.data import interfaces
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grant_recipients import get_grant_recipients
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.forms import GrantChangeGGISForm, GrantContactForm, GrantDescriptionForm, GrantNameForm
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details", methods=["GET"])
@has_deliver_grant_role(RoleEnum.MEMBER)
def grant_details(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template(
        "deliver_grant_funding/grant_details.html",
        grant=grant,
        roles_enum=RoleEnum,
        grant_recipients=get_grant_recipients(
            grant, with_data_providers=True, with_certifiers=True, with_organisations=True
        ),
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details/change-ggis", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def grant_change_ggis(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantChangeGGISForm(ggis_number=grant.ggis_number)

    if form.validate_on_submit():
        ggis_number = form.ggis_number.data or ""
        interfaces.grants.update_grant(grant=grant, ggis_number=ggis_number)
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/grant_setup/grant_change_ggis.html",
        form=form,
        back_link_href=url_for("deliver_grant_funding.grant_details", grant_id=grant_id),
        grant=grant,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details/change-name", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def grant_change_name(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantNameForm(obj=grant, existing_grant_id=grant_id, is_update=True)

    if form.validate_on_submit():
        try:
            assert form.name.data is not None, "Grant name must be provided"
            interfaces.grants.update_grant(grant=grant, name=form.name.data)
            return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/grant_setup/grant_name.html",
        form=form,
        back_link_href=url_for("deliver_grant_funding.grant_details", grant_id=grant_id),
        grant=grant,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details/change-description", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def grant_change_description(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantDescriptionForm(obj=grant, is_update=True)

    if form.validate_on_submit():
        assert form.description.data is not None, "Grant description must be provided"
        interfaces.grants.update_grant(grant=grant, description=form.description.data)
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/grant_setup/grant_description.html",
        form=form,
        back_link_href=url_for("deliver_grant_funding.grant_details", grant_id=grant_id),
        grant=grant,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details/change-contact", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def grant_change_contact(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantContactForm(obj=grant, is_update=True)

    if form.validate_on_submit():
        assert form.primary_contact_name.data, "Primary contact name must be provided"
        assert form.primary_contact_email.data, "Primary contact email must be provided"
        interfaces.grants.update_grant(
            grant=grant,
            primary_contact_name=form.primary_contact_name.data,
            primary_contact_email=form.primary_contact_email.data,
        )
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/grant_setup/grant_main_contact.html",
        form=form,
        back_link_href=url_for("deliver_grant_funding.grant_details", grant_id=grant_id),
        grant=grant,
    )
