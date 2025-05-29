from uuid import UUID

from flask import Blueprint, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.auth.decorators import mhclg_login_required, platform_admin_role_required
from app.common.data import interfaces
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.deliver_grant_funding.forms import (
    GrantContactForm,
    GrantDescriptionForm,
    GrantForm,
    GrantGGISForm,
    GrantNameSetupForm,
    GrantSetupIntroForm,
)
from app.extensions import auto_commit_after_request

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)


@deliver_grant_funding_blueprint.route("/grants/add", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_intro() -> ResponseReturnValue:
    form = GrantSetupIntroForm()
    if form.validate_on_submit():
        session.pop("grant_setup", None)
        session["grant_setup"] = {}
        return redirect(url_for("deliver_grant_funding.grant_setup_ggis"))
    return render_template("deliver_grant_funding/grant_setup/intro.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/add/ggis-number", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_ggis() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    form_data = session["grant_setup"].get("ggis", {})
    form = GrantGGISForm(data=form_data)

    if form.validate_on_submit():
        session["grant_setup"]["ggis"] = {
            "has_ggis": form.has_ggis.data,
            "ggis_number": form.ggis_number.data if form.has_ggis.data == "yes" else None,
        }
        session.modified = True
        return redirect(url_for("deliver_grant_funding.grant_setup_name"))

    return render_template("deliver_grant_funding/grant_setup/ggis_number.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/add/name", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_name() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    form_data = session["grant_setup"].get("name", {})
    form = GrantNameSetupForm(data=form_data)

    if form.validate_on_submit():
        session["grant_setup"]["name"] = {"name": form.name.data}
        session.modified = True
        return redirect(url_for("deliver_grant_funding.grant_setup_description"))

    return render_template("deliver_grant_funding/grant_setup/name.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/add/description", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_description() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    form_data = session["grant_setup"].get("description", {})
    form = GrantDescriptionForm(data=form_data)

    if form.validate_on_submit():
        session["grant_setup"]["description"] = {"description": form.description.data}
        session.modified = True
        return redirect(url_for("deliver_grant_funding.grant_setup_contact"))

    return render_template("deliver_grant_funding/grant_setup/description.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/add/contact", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def grant_setup_contact() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    form_data = session["grant_setup"].get("contact", {})
    form = GrantContactForm(data=form_data)

    if form.validate_on_submit():
        try:
            grant_data = session.get("grant_setup", {})

            grant = interfaces.grants.create_grant(
                name=grant_data.get("name", {}).get("name", ""),
                ggis_number=grant_data.get("ggis", {}).get("ggis_number"),
                description=grant_data.get("description", {}).get("description"),
                primary_contact_name=form.primary_contact_name.data,
                primary_contact_email=form.primary_contact_email.data,
            )

            session.pop("grant_setup", None)

            return redirect(url_for("deliver_grant_funding.view_grant", grant_id=grant.id))

        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template("deliver_grant_funding/grant_setup/contact.html", form=form)


@deliver_grant_funding_blueprint.route("/grants", methods=["GET"])
@mhclg_login_required
def list_grants() -> str:
    grants = interfaces.grants.get_all_grants()
    return render_template("deliver_grant_funding/grant_list.html", grants=grants)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
@mhclg_login_required
def view_grant(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_view.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/settings", methods=["GET"])
@mhclg_login_required
def grant_settings(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_settings.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/change-name", methods=["GET", "POST"])
@mhclg_login_required
@auto_commit_after_request
def grant_change_name(grant_id: UUID) -> str | Response:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantForm(obj=grant)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            interfaces.grants.update_grant(grant=grant, name=form.name.data)
            return redirect(url_for("deliver_grant_funding.grant_settings", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("deliver_grant_funding/settings/grant_change_name.html", form=form, grant=grant)
