import uuid
from typing import cast

import sentry_sdk
from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import login_user, logout_user

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import redirect_if_authenticated
from app.common.auth.forms import SignInForm
from app.common.auth.sso import MSAL_ERROR_AUTHORIZATION_CODE_WAS_ALREADY_REDEEMED, build_auth_code_flow, build_msal_app
from app.common.data import interfaces
from app.common.data.types import AuthMethodEnum
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

        internal_domains = current_app.config["INTERNAL_DOMAINS"]
        if email.endswith(internal_domains):
            session["magic_link_redirect"] = True
            return redirect(url_for("auth.sso_sign_in"))

        user = interfaces.user.get_user_by_email(email_address=email)

        # The default url for access.grants_list is currently restricted to platform admins only, but using here in lieu
        # of a formal landing page for Access Grant Funding users
        magic_link = interfaces.magic_link.create_magic_link(
            user=user,
            email=email,
            redirect_to_path=sanitise_redirect_url(session.pop("next", url_for("developers.access.grants_list"))),
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
    if not magic_link or not magic_link.is_usable:
        return abort(404)

    notification_id = session.pop("magic_link_email_notification_id", None)
    return render_template("common/auth/check_email.html", email=magic_link.email, notification_id=notification_id)


@auth_blueprint.route("/sign-in/<magic_link_code>", methods=["GET", "POST"])
@redirect_if_authenticated
@auto_commit_after_request
def claim_magic_link(magic_link_code: str) -> ResponseReturnValue:
    magic_link = interfaces.magic_link.get_magic_link(code=magic_link_code)
    if not magic_link or not magic_link.is_usable:
        if magic_link:
            session["next"] = magic_link.redirect_to_path
        return redirect(
            url_for(
                "auth.request_a_link_to_sign_in",
                link_expired=True,
            )
        )

    form = GenericSubmitForm()
    if form.validate_on_submit():
        user = magic_link.user
        if not user:
            user = interfaces.user.upsert_user_by_email(email_address=str(magic_link.email))
        interfaces.magic_link.claim_magic_link(magic_link=magic_link, user=user)
        if not login_user(user):
            return abort(400)

        session["auth"] = AuthMethodEnum.MAGIC_LINK
        return redirect(sanitise_redirect_url(magic_link.redirect_to_path))

    return render_template("common/auth/claim_magic_link.html", form=form, magic_link=magic_link)


@auth_blueprint.route("/sso/permissions-error", methods=["GET", "POST"])
def signed_in_but_no_permissions() -> ResponseReturnValue:
    return render_template(
        "common/auth/mhclg-user-not-authorised.html",
        service_desk_url=current_app.config["DELIVER_SERVICE_DESK_URL"],
        invite_expired=str(request.args.get("invite_expired", False)) == "True",
    ), 403


@auth_blueprint.route("/sso/sign-in", methods=["GET", "POST"])
@redirect_if_authenticated
def sso_sign_in() -> ResponseReturnValue:
    form = GenericSubmitForm()
    magic_link_redirect = session.pop("magic_link_redirect", False)
    if form.validate_on_submit():
        session["flow"] = build_auth_code_flow(scopes=current_app.config["MS_GRAPH_PERMISSIONS_SCOPE"])
        return redirect(session["flow"]["auth_uri"]), 302
    return render_template("common/auth/sign_in_sso.html", form=form, magic_link_redirect=magic_link_redirect)


@auth_blueprint.route("/sso/get-token", methods=["GET"])
@redirect_if_authenticated
@auto_commit_after_request
def sso_get_token() -> ResponseReturnValue:
    result = build_msal_app().acquire_token_by_auth_code_flow(session.get("flow", {}), request.args)
    if "error" in result:
        if MSAL_ERROR_AUTHORIZATION_CODE_WAS_ALREADY_REDEEMED in result.get("error_codes", []):
            current_app.logger.warning(
                "Authorization code was already redeemed: %(error)s.", {"error": result.get("error_description")}
            )
            return redirect(url_for("auth.sign_out"))
        return abort(500, "Azure AD get-token flow failed with: {}".format(result))

    sso_user = result["id_token_claims"]

    # Does the user exist already?
    user = interfaces.user.get_user_by_azure_ad_subject_id(azure_ad_subject_id=sso_user["sub"])

    # Platform admin route
    if "FS_PLATFORM_ADMIN" in sso_user.get("roles", []):
        user = interfaces.user.upsert_user_and_set_platform_admin_role(
            azure_ad_subject_id=sso_user["sub"], email_address=sso_user["preferred_username"], name=sso_user["name"]
        )

    # Invitations route
    elif user is None:
        user_invites = interfaces.user.get_usable_invitations_by_email(email=sso_user["preferred_username"])
        if not user_invites:
            all_invites = interfaces.user.get_invitations_by_email(email=sso_user["preferred_username"])
            return redirect(
                url_for("auth.signed_in_but_no_permissions", invite_expired=len(all_invites) > 0),
            )
        user = interfaces.user.create_user_and_claim_invitations(
            azure_ad_subject_id=sso_user["sub"],
            email_address=sso_user["preferred_username"],
            name=sso_user["name"],
        )

    # Existing User with roles route
    elif user and user.roles:
        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id=sso_user["sub"],
            email_address=sso_user["preferred_username"],
            name=sso_user["name"],
        )
        if AuthorisationHelper.is_platform_admin(user):
            interfaces.user.remove_platform_admin_role_from_user(user)
            if not user.roles:
                return redirect(
                    url_for("auth.signed_in_but_no_permissions", invite_expired=False),
                )

    # No user and no roles means they should 403 for now
    else:
        return redirect(
            url_for("auth.signed_in_but_no_permissions", invite_expired=False),
        )

    # For all other valid users with roles after the above, finish the flow and redirect
    redirect_to_path = sanitise_redirect_url(session.pop("next", url_for("index")))
    session.pop("flow", None)

    if not login_user(user):
        return abort(400)

    session["auth"] = AuthMethodEnum.SSO

    return redirect(redirect_to_path)


@auth_blueprint.get("/sign-out")
def sign_out() -> ResponseReturnValue:
    logout_user()
    sentry_sdk.set_user(None)

    return redirect(url_for("index"))
