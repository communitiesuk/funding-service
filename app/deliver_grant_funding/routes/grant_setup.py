from flask import redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.decorators import is_platform_admin
from app.common.data import interfaces
from app.common.forms import GenericSubmitForm
from app.constants import CHECK_YOUR_ANSWERS
from app.deliver_grant_funding.forms import GrantContactForm, GrantDescriptionForm, GrantGGISForm, GrantNameForm
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.deliver_grant_funding.session_models import GrantSetupSession
from app.extensions import auto_commit_after_request


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
