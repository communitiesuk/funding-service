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
    GrantGGISForm,
    GrantNameForm,
    GrantSetupIntroForm,
)
from app.deliver_grant_funding.session_models import GrantSetupSession
from app.extensions import auto_commit_after_request, notification_service

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)

CHECK_YOUR_ANSWERS = "check-your-answers"


@deliver_grant_funding_blueprint.route("/grant-setup", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_intro() -> ResponseReturnValue:
    form = GrantSetupIntroForm()
    if form.validate_on_submit():
        grant_session = GrantSetupSession()
        session["grant_setup"] = grant_session.to_session_dict()
        return redirect(url_for("deliver_grant_funding.grant_setup_ggis"))
    return render_template("deliver_grant_funding/grant_setup/initial_flow/intro.html", form=form)


@deliver_grant_funding_blueprint.route("/grant-setup/ggis-number", methods=["GET", "POST"])
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

    back_href = (
        url_for("deliver_grant_funding.grant_setup_check_your_answers")
        if request.args.get("source") == CHECK_YOUR_ANSWERS
        else url_for("deliver_grant_funding.grant_setup_intro")
    )
    return render_template(
        "deliver_grant_funding/grant_setup/grant_ggis.html",
        form=form,
        back_link_href=back_href,
    )


@deliver_grant_funding_blueprint.route("/grant-setup/name", methods=["GET", "POST"])
@platform_admin_role_required
def grant_setup_name() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GrantNameForm(
        obj=grant_session,
    )

    if form.validate_on_submit():
        assert form.name.data is not None, "Grant name must be provided"
        grant_session.name = form.name.data
        session["grant_setup"] = grant_session.to_session_dict()
        if request.args.get("source") == CHECK_YOUR_ANSWERS:
            return redirect(url_for("deliver_grant_funding.grant_setup_check_your_answers"))
        return redirect(url_for("deliver_grant_funding.grant_setup_description"))

    back_href = (
        url_for("deliver_grant_funding.grant_setup_check_your_answers")
        if request.args.get("source") == CHECK_YOUR_ANSWERS
        else url_for("deliver_grant_funding.grant_setup_ggis")
    )
    return render_template(
        "deliver_grant_funding/grant_setup/grant_name.html",
        form=form,
        back_link_href=back_href,
    )


@deliver_grant_funding_blueprint.route("/grant-setup/description", methods=["GET", "POST"])
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

    back_href = (
        url_for("deliver_grant_funding.grant_setup_check_your_answers")
        if request.args.get("source") == CHECK_YOUR_ANSWERS
        else url_for("deliver_grant_funding.grant_setup_name")
    )
    return render_template(
        "deliver_grant_funding/grant_setup/grant_description.html",
        form=form,
        back_link_href=back_href,
    )


@deliver_grant_funding_blueprint.route("/grant-setup/contact", methods=["GET", "POST"])
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

    back_href = (
        url_for("deliver_grant_funding.grant_setup_check_your_answers")
        if request.args.get("source") == CHECK_YOUR_ANSWERS
        else url_for("deliver_grant_funding.grant_setup_description")
    )
    return render_template(
        "deliver_grant_funding/grant_setup/grant_main_contact.html",
        form=form,
        back_link_href=back_href,
    )


@deliver_grant_funding_blueprint.route("/grant-setup/check-your-answers", methods=["GET", "POST"])
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
        "deliver_grant_funding/grant_setup/initial_flow/check_your_answers.html",
        form=form,
        grant_session=grant_session,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grant-setup/<uuid:grant_id>", methods=["GET"])
@platform_admin_role_required
def grant_setup_confirmation(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_setup/initial_flow/confirmation.html", grant=grant)


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


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>", methods=["GET"])
@mhclg_login_required
def view_grant(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_view.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/users", methods=["GET"])
@mhclg_login_required
def list_users_for_grant(grant_id: UUID) -> ResponseReturnValue:
    try:
        grant = interfaces.grants.get_grant(grant_id)
    except NoResultFound:
        abort(404)
    return render_template(
        "deliver_grant_funding/grant_team/grant_user_list.html",
        grant=grant,
        service_desk_url=current_app.config["SERVICE_DESK_URL"],
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/users/add", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def add_user_to_grant(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantAddUserForm(grant=grant)
    if form.validate_on_submit():
        if form.user_email.data:
            user = next((user for user in grant.users if user.email.lower() == form.user_email.data.lower()), None)
            if user is None:
                created_user = interfaces.user.upsert_user_by_email(email_address=form.user_email.data)
                interfaces.user.upsert_user_role(user_id=created_user.id, grant_id=grant_id, role=RoleEnum.MEMBER)
                notification_service.send_member_confirmation(
                    grant_name=grant.name,
                    email_address=form.user_email.data,
                )
                flash("We’ve emailed the grant team member a link to sign in")
            return redirect(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant_id))
    return render_template("deliver_grant_funding/grant_team/grant_user_add.html", form=form, grant=grant)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details", methods=["GET"])
@mhclg_login_required
def grant_details(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_details.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details/change-ggis", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def grant_change_ggis(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantGGISForm(has_ggis=("yes" if grant.ggis_number else "no"), ggis_number=grant.ggis_number, is_update=True)

    if form.validate_on_submit():
        ggis_number = form.ggis_number.data if form.has_ggis.data == "yes" else None
        interfaces.grants.update_grant(grant=grant, ggis_number=ggis_number)
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/grant_setup/grant_ggis.html",
        form=form,
        back_link_href=url_for("deliver_grant_funding.grant_details", grant_id=grant_id),
        grant=grant,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details/change-name", methods=["GET", "POST"])
@platform_admin_role_required
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
@platform_admin_role_required
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
@platform_admin_role_required
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
