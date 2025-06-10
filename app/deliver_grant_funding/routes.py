from uuid import UUID

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import NoResultFound
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.auth.decorators import mhclg_login_required, platform_admin_role_required
from app.common.data import interfaces
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.forms import (
    GrantAddUserForm,
    GrantCheckYourAnswersForm,
    GrantContactForm,
    GrantDescriptionForm,
    GrantForm,
    GrantGGISForm,
    GrantNameForm,
    GrantSetupIntroForm,
)
from app.deliver_grant_funding.session_models import GrantSetupSession
from app.extensions import auto_commit_after_request, notification_service

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)

CHECK_YOUR_ANSWERS = "check-your-answers"


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
    form = GrantGGISForm(obj=grant_session)

    if form.validate_on_submit():
        grant_session.has_ggis = form.has_ggis.data
        grant_session.ggis_number = form.ggis_number.data if form.has_ggis.data == "yes" else None
        session["grant_setup"] = grant_session.to_session_dict()
        if request.args.get("source") == CHECK_YOUR_ANSWERS:
            return redirect(url_for("deliver_grant_funding.grant_setup_check_your_answers"))
        return redirect(url_for("deliver_grant_funding.grant_setup_name"))

    return render_template(
        "deliver_grant_funding/grant_setup/ggis_number.html",
        form=form,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grants/setup/name", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_name() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GrantNameForm(obj=grant_session)

    if form.validate_on_submit():
        assert form.name.data is not None, "Grant name must be provided"
        grant_session.name = form.name.data
        session["grant_setup"] = grant_session.to_session_dict()
        if request.args.get("source") == CHECK_YOUR_ANSWERS:
            return redirect(url_for("deliver_grant_funding.grant_setup_check_your_answers"))
        return redirect(url_for("deliver_grant_funding.grant_setup_description"))

    return render_template(
        "deliver_grant_funding/grant_setup/name.html",
        form=form,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grants/setup/description", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_description() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GrantDescriptionForm(obj=grant_session)

    if form.validate_on_submit():
        assert form.description.data is not None, "Grant description must be provided"
        grant_session.description = form.description.data
        session["grant_setup"] = grant_session.to_session_dict()
        if request.args.get("source") == CHECK_YOUR_ANSWERS:
            return redirect(url_for("deliver_grant_funding.grant_setup_check_your_answers"))
        return redirect(url_for("deliver_grant_funding.grant_setup_contact"))

    return render_template(
        "deliver_grant_funding/grant_setup/description.html",
        form=form,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grants/setup/contact", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_contact() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GrantContactForm(obj=grant_session)

    if form.validate_on_submit():
        assert form.primary_contact_name.data, "Primary contact name must be provided"
        assert form.primary_contact_email.data, "Primary contact email must be provided"
        grant_session.primary_contact_name = form.primary_contact_name.data
        grant_session.primary_contact_email = form.primary_contact_email.data
        session["grant_setup"] = grant_session.to_session_dict()
        return redirect(url_for("deliver_grant_funding.grant_setup_check_your_answers"))

    return render_template(
        "deliver_grant_funding/grant_setup/contact.html",
        form=form,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grants/setup/check-your-answers", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def grant_setup_check_your_answers() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GrantCheckYourAnswersForm()

    if form.validate_on_submit():
        grant = interfaces.grants.create_grant(
            name=grant_session.name,
            description=grant_session.description,
            primary_contact_name=grant_session.primary_contact_name,
            primary_contact_email=grant_session.primary_contact_email,
            ggis_number=grant_session.ggis_number,
        )
        session.pop("grant_setup", None)
        return redirect(url_for("deliver_grant_funding.grant_setup_confirmation", grant_id=grant.id))

    return render_template(
        "deliver_grant_funding/grant_setup/check_your_answers.html",
        form=form,
        grant_session=grant_session,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/setup-confirmation", methods=["GET"])
@platform_admin_role_required
def grant_setup_confirmation(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_setup/confirmation.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants", methods=["GET"])
@mhclg_login_required
def list_grants() -> Response | str:
    user = interfaces.user.get_current_user()
    grants = interfaces.grants.get_all_grants_by_user(user=user)
    # TODO if the user is a MEMBER and does not have any grant we need to handle that but if you are a
    #  ADMIN then should be able to see grants or empty page with create grant feature
    if len(grants) == 1 and not user.is_platform_admin:
        return redirect(url_for("deliver_grant_funding.view_grant", grant_id=grants[0].id))
    return render_template("deliver_grant_funding/grant_list.html", grants=grants)


@deliver_grant_funding_blueprint.route("/grant/users/<uuid:grant_id>", methods=["GET"])
@mhclg_login_required
def list_users_for_grant(grant_id: UUID) -> str:
    try:
        grant = interfaces.grants.get_grant(grant_id)
    except NoResultFound:
        abort(404)
    grant_users = [
        role.user for role in grant.roles if role.role == RoleEnum.MEMBER and not role.user.is_platform_admin
    ]
    return render_template(
        "deliver_grant_funding/grant_team/grant_user_list.html",
        grant=grant,
        users=grant_users,
        service_desk_url=current_app.config["SERVICE_DESK_URL"],
    )


@deliver_grant_funding_blueprint.route("/grant/share/user/<uuid:grant_id>", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def add_user_to_grant(grant_id: UUID) -> ResponseReturnValue:
    form = GrantAddUserForm()
    grant = interfaces.grants.get_grant(grant_id)
    if form.validate_on_submit():
        if form.user_email.data:
            user = next((role for role in grant.roles if role.user.email == form.user_email.data), None)
            if user is None:
                created_user = interfaces.user.get_or_create_user(email_address=form.user_email.data)
                user_role = interfaces.user.add_user_role(
                    user_id=created_user.id, grant_id=grant_id, role=RoleEnum.MEMBER
                )
                if user_role:
                    notification_service.send_member_confirmation(
                        grant_name=grant.name,
                        email_address=form.user_email.data,
                        sign_in_url=url_for("auth.sso_sign_in", _external=True),
                    )
                    flash("We’ve emailed the grant team member a link to sign in")
            return redirect(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant_id))
    return render_template("deliver_grant_funding/grant_team/grant_user_add.html", form=form, grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
@mhclg_login_required
def view_grant(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_view.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/settings", methods=["GET"])
@mhclg_login_required
def grant_settings(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_details.html", grant=grant)


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
