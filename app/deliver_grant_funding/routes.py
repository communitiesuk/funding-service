from uuid import UUID

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import NoResultFound
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_grant_role, is_mhclg_user, is_platform_admin
from app.common.data import interfaces
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.types import RoleEnum
from app.common.forms import GenericSubmitForm
from app.deliver_grant_funding.forms import (
    GrantAddUserForm,
    GrantChangeGGISForm,
    GrantContactForm,
    GrantDescriptionForm,
    GrantGGISForm,
    GrantNameForm,
)
from app.deliver_grant_funding.session_models import GrantSetupSession
from app.extensions import auto_commit_after_request, notification_service

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)

CHECK_YOUR_ANSWERS = "check-your-answers"


@deliver_grant_funding_blueprint.route("/grant-setup", methods=["GET", "POST"])
@is_platform_admin
def grant_setup_intro() -> ResponseReturnValue:
    form = GenericSubmitForm()
    if form.validate_on_submit():
        grant_session = GrantSetupSession()
        session["grant_setup"] = grant_session.to_session_dict()
        return redirect(url_for("deliver_grant_funding.grant_setup_ggis"))
    return render_template("deliver_grant_funding/grant_setup/initial_flow/intro.html", form=form)


@deliver_grant_funding_blueprint.route("/grant-setup/ggis-number", methods=["GET", "POST"])
@is_platform_admin
def grant_setup_ggis() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GrantGGISForm(obj=grant_session)

    if form.validate_on_submit():
        if form.has_ggis.data == "no":
            return redirect(url_for("deliver_grant_funding.grant_setup_ggis_required_info"))

        grant_session.has_ggis = form.has_ggis.data
        grant_session.ggis_number = form.ggis_number.data or ""
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


@deliver_grant_funding_blueprint.route("/grant-setup/ggis-required-info", methods=["GET"])
@is_platform_admin
def grant_setup_ggis_required_info() -> ResponseReturnValue:
    return render_template(
        "deliver_grant_funding/grant_setup/ggis_required_info.html",
        back_link_href=url_for("deliver_grant_funding.grant_setup_ggis"),
    )


@deliver_grant_funding_blueprint.route("/grant-setup/name", methods=["GET", "POST"])
@is_platform_admin
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
@is_platform_admin
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
@is_platform_admin
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
@is_platform_admin
@auto_commit_after_request
def grant_setup_check_your_answers() -> ResponseReturnValue:
    if "grant_setup" not in session:
        return redirect(url_for("deliver_grant_funding.grant_setup_intro"))

    grant_session = GrantSetupSession.from_session(session["grant_setup"])
    form = GenericSubmitForm()

    if form.validate_on_submit():
        grant = interfaces.grants.create_grant(
            name=grant_session.name,
            description=grant_session.description,
            primary_contact_name=grant_session.primary_contact_name,
            primary_contact_email=grant_session.primary_contact_email,
            ggis_number=grant_session.ggis_number,
        )
        session.pop("grant_setup", None)
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant.id))

    return render_template(
        "deliver_grant_funding/grant_setup/initial_flow/check_your_answers.html",
        form=form,
        grant_session=grant_session,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
    )


@deliver_grant_funding_blueprint.route("/grants", methods=["GET"])
@is_mhclg_user
def list_grants() -> Response | str:
    user = interfaces.user.get_current_user()
    grants = interfaces.grants.get_all_grants_by_user(user=user)
    # TODO if the user is a MEMBER and does not have any grant we need to handle that but if you are a
    #  ADMIN then should be able to see grants or empty page with create grant feature
    if len(grants) == 1 and not AuthorisationHelper.is_platform_admin(user):
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grants[0].id))
    return render_template("deliver_grant_funding/grant_list.html", grants=grants)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/users", methods=["GET"])
@has_grant_role(RoleEnum.MEMBER)
def list_users_for_grant(grant_id: UUID) -> ResponseReturnValue:
    try:
        grant = interfaces.grants.get_grant(grant_id)
    except NoResultFound:
        return abort(404)
    return render_template(
        "deliver_grant_funding/grant_team/grant_user_list.html",
        grant=grant,
        service_desk_url=current_app.config["SERVICE_DESK_URL"],
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/users/add", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def add_user_to_grant(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantAddUserForm(grant=grant)
    if form.validate_on_submit():
        if form.user_email.data:
            # are they already in this grant - if so, redirect to the list of users
            grant_user = next(
                (user for user in grant.users if user.email.lower() == form.user_email.data.lower()), None
            )
            if grant_user:
                return redirect(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant_id))
            interfaces.user.add_grant_member_role_or_create_invitation(email_address=form.user_email.data, grant=grant)
            notification_service.send_member_confirmation(
                grant=grant,
                email_address=form.user_email.data,
            )
            flash("We’ve emailed the grant team member a link to sign in")
            return redirect(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant_id))

    return render_template("deliver_grant_funding/grant_team/grant_user_add.html", form=form, grant=grant)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/details", methods=["GET"])
@has_grant_role(RoleEnum.MEMBER)
def grant_details(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_details.html", grant=grant, roles_enum=RoleEnum)


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
@has_grant_role(RoleEnum.ADMIN)
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
@has_grant_role(RoleEnum.ADMIN)
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
@has_grant_role(RoleEnum.ADMIN)
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
