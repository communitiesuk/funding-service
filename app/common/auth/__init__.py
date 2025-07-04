import uuid
from typing import cast

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import login_user, logout_user

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import redirect_if_authenticated
from app.common.auth.forms import SignInForm
from app.common.auth.sso import build_auth_code_flow, build_msal_app
from app.common.data import interfaces
from app.common.forms import GenericSubmitForm
from app.common.security.utils import sanitise_redirect_url
from app.extensions import auto_commit_after_request, notification_service

auth_blueprint = Blueprint(
    "auth",
    __name__,
    url_prefix="/",
)


@auth_blueprint.route("/request-a-link-to-sign-in", methods=["GET", "POST"])
@redirect_if_authenticated
@auto_commit_after_request
def request_a_link_to_sign_in() -> ResponseReturnValue:
    form = SignInForm()
    link_expired = request.args.get("link_expired", False)
    if form.validate_on_submit():
        email = cast(str, form.email_address.data)
        user = interfaces.user.get_user_by_email(email_address=email)
        magic_link = interfaces.magic_link.create_magic_link(
            user=user if user else None,
            email=email,
            redirect_to_path=sanitise_redirect_url(session.pop("next", url_for("index"))),
        )

        notification = notification_service.send_magic_link(
            email,
            magic_link_url=url_for("auth.claim_magic_link", magic_link_code=magic_link.code, _external=True),
            magic_link_expires_at_utc=magic_link.expires_at_utc,
            request_new_magic_link_url=url_for("auth.request_a_link_to_sign_in", _external=True),
        )
        session["magic_link_email_notification_id"] = notification.id

        return redirect(url_for("auth.check_email", magic_link_id=magic_link.id))

    return render_template("common/auth/sign_in_magic_link.html", form=form, link_expired=link_expired)


@auth_blueprint.get("/check-your-email/<uuid:magic_link_id>")
@redirect_if_authenticated
def check_email(magic_link_id: uuid.UUID) -> ResponseReturnValue:
    magic_link = interfaces.magic_link.get_magic_link(id_=magic_link_id)
    if not magic_link:
        abort(404)

    notification_id = session.pop("magic_link_email_notification_id", None)
    return render_template("common/auth/check_email.html", user=magic_link.user, notification_id=notification_id)


@auth_blueprint.route("/sign-in/<magic_link_code>", methods=["GET", "POST"])
@redirect_if_authenticated
@auto_commit_after_request
def claim_magic_link(magic_link_code: str) -> ResponseReturnValue:
    magic_link = interfaces.magic_link.get_magic_link(code=magic_link_code)
    if not magic_link:
        return redirect(url_for("auth.request_a_link_to_sign_in", link_expired=True))

    form = GenericSubmitForm()
    if form.validate_on_submit():
        user = interfaces.user.upsert_user_by_email(email_address=str(magic_link.email))
        interfaces.magic_link.claim_magic_link(magic_link=magic_link, user=user)
        if not login_user(magic_link.user):
            abort(400)

        return redirect(sanitise_redirect_url(magic_link.redirect_to_path))

    return render_template("common/auth/claim_magic_link.html", form=form, magic_link=magic_link)


@auth_blueprint.route("/sso/sign-in", methods=["GET", "POST"])
@redirect_if_authenticated
def sso_sign_in() -> ResponseReturnValue:
    form = GenericSubmitForm()
    if form.validate_on_submit():
        session["flow"] = build_auth_code_flow(scopes=current_app.config["MS_GRAPH_PERMISSIONS_SCOPE"])
        return redirect(session["flow"]["auth_uri"]), 302
    return render_template("common/auth/sign_in_sso.html", form=form)


@auth_blueprint.route("/sso/get-token", methods=["GET"])
@redirect_if_authenticated
@auto_commit_after_request
def sso_get_token() -> ResponseReturnValue:
    result = build_msal_app().acquire_token_by_auth_code_flow(session.get("flow", {}), request.args)

    if "error" in result:
        return abort(500, "Azure AD get-token flow failed with: {}".format(result))

    sso_user = result["id_token_claims"]
    user = interfaces.user.get_user_by_azure_ad_subject_id(azure_ad_subject_id=sso_user["sub"])
    # TODO: FSPT-515 - remove this logic. This additional logic is to cover grant team members who are directly added as
    # users but don't yet have the azure_ad_subject_id field present as they haven't logged in. Our SSO now uses this as
    # the unique identifying field so needs it to be present. This should be removed when we move to an invitation
    # mechanism in FSPT-515 which won't create a User in the database until they sign in for the first time, allowing us
    # to simplify this flow.
    if user is None:
        user = interfaces.user.get_user_by_email(email_address=sso_user["preferred_username"])
        if user and not user.azure_ad_subject_id:
            user = interfaces.user.upsert_user_by_email(
                email_address=sso_user["preferred_username"],
                name=sso_user["name"],
                azure_ad_subject_id=sso_user["sub"],
            )
    redirect_to_path = sanitise_redirect_url(session.pop("next", url_for("index")))

    if "FSD_ADMIN" in sso_user.get("roles", []):
        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id=sso_user["sub"],
            email_address=sso_user["preferred_username"],
            name=sso_user["name"],
        )
        interfaces.user.set_platform_admin_role_for_user(user)
    elif user and user.roles:
        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id=sso_user["sub"],
            email_address=sso_user["preferred_username"],
            name=sso_user["name"],
        )
        if AuthorisationHelper.is_platform_admin(user):
            interfaces.user.remove_platform_admin_role_from_user(user)
            if not user.roles:
                return render_template(
                    "common/auth/mhclg-user-not-authorised.html",
                    service_desk_url=current_app.config["SERVICE_DESK_URL"],
                ), 403
    else:
        return render_template(
            "common/auth/mhclg-user-not-authorised.html", service_desk_url=current_app.config["SERVICE_DESK_URL"]
        ), 403

    session.pop("flow", None)

    if not login_user(user):
        abort(400)

    return redirect(redirect_to_path)


@auth_blueprint.get("/sign-out")
def sign_out() -> ResponseReturnValue:
    logout_user()

    return redirect(url_for("index"))
