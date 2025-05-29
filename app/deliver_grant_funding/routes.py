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
    GrantNameForm,
    GrantSetupIntroForm,
)
from app.deliver_grant_funding.session_models import (
    GrantSetupContact,
    GrantSetupDescription,
    GrantSetupGGIS,
    GrantSetupName,
    GrantSetupSession,
)
from app.extensions import auto_commit_after_request

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)


@deliver_grant_funding_blueprint.route("/grants/setup", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_intro() -> ResponseReturnValue:
    form = GrantSetupIntroForm()
    if form.validate_on_submit():
        grant_session = GrantSetupSession()
        session["grant_setup"] = grant_session.to_session_dict()
        return redirect(url_for("deliver_grant_funding.grant_setup_ggis"))
    return render_template("deliver_grant_funding/grant_setup/intro.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/setup/ggis-number", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_ggis() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form_data = grant_session.ggis.model_dump() if grant_session.ggis else {}
    form = GrantGGISForm(data=form_data)

    if form.validate_on_submit():
        grant_session.ggis = GrantSetupGGIS(
            has_ggis=form.has_ggis.data,
            ggis_number=form.ggis_number.data if form.has_ggis.data == "yes" else None,
        )
        session["grant_setup"] = grant_session.to_session_dict()
        session.modified = True
        return redirect(url_for("deliver_grant_funding.grant_setup_name"))

    return render_template("deliver_grant_funding/grant_setup/ggis_number.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/setup/name", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_name() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form_data = grant_session.name.model_dump() if grant_session.name else {}
    form = GrantNameForm(data=form_data)

    if form.validate_on_submit():
        assert form.name.data is not None, "Grant name must be provided"
        grant_session.name = GrantSetupName(name=form.name.data)
        session["grant_setup"] = grant_session.to_session_dict()
        session.modified = True
        return redirect(url_for("deliver_grant_funding.grant_setup_description"))

    return render_template("deliver_grant_funding/grant_setup/name.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/setup/description", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_description() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form_data = grant_session.description.model_dump() if grant_session.description else {}
    form = GrantDescriptionForm(data=form_data)

    if form.validate_on_submit():
        assert form.description.data is not None, "Grant description must be provided"
        grant_session.description = GrantSetupDescription(description=form.description.data)
        session["grant_setup"] = grant_session.to_session_dict()
        session.modified = True
        return redirect(url_for("deliver_grant_funding.grant_setup_contact"))

    return render_template("deliver_grant_funding/grant_setup/description.html", form=form)


@deliver_grant_funding_blueprint.route("/grants/setup/contact", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def grant_setup_contact() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form_data = grant_session.contact.model_dump() if grant_session.contact else {}
    form = GrantContactForm(data=form_data)

    if form.validate_on_submit():
        try:
            assert form.primary_contact_name.data, "Primary contact name must be provided"
            assert form.primary_contact_email.data, "Primary contact email must be provided"
            grant_session.contact = GrantSetupContact(
                primary_contact_name=form.primary_contact_name.data,
                primary_contact_email=form.primary_contact_email.data,
            )

            grant = interfaces.grants.create_grant(
                name=grant_session.name.name if grant_session.name else "",
                ggis_number=grant_session.ggis.ggis_number if grant_session.ggis else None,
                description=grant_session.description.description if grant_session.description else "",
                primary_contact_name=grant_session.contact.primary_contact_name,
                primary_contact_email=grant_session.contact.primary_contact_email,
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
