import uuid
from typing import cast

from flask import Blueprint, abort, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import login_user, logout_user

from app.common.auth.forms import ClaimMagicLinkForm, SignInForm
from app.common.data import interfaces
from app.common.data.interfaces.user import get_or_create_user
from app.common.security.utils import sanitise_redirect_url
from app.extensions import auto_commit_after_request, notification_service

auth_blueprint = Blueprint(
    "auth",
    __name__,
    url_prefix="/",
)


@auth_blueprint.route("/request-a-link-to-sign-in", methods=["GET", "POST"])
@auto_commit_after_request
def request_a_link_to_sign_in() -> ResponseReturnValue:
    form = SignInForm()
    if form.validate_on_submit():
        email = cast(str, form.email_address.data)

        user = get_or_create_user(email_address=email)
        magic_link = interfaces.magic_link.create_magic_link(
            user=user,
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

    return render_template("common/auth/sign_in.html", form=form)


@auth_blueprint.get("/check-your-email/<uuid:magic_link_id>")
def check_email(magic_link_id: uuid.UUID) -> ResponseReturnValue:
    magic_link = interfaces.magic_link.get_magic_link(id_=magic_link_id)
    if not magic_link or not magic_link.usable:
        abort(404)

    notification_id = session.pop("magic_link_email_notification_id", None)
    return render_template("common/auth/check_email.html", user=magic_link.user, notification_id=notification_id)


@auth_blueprint.route("/sign-in/<magic_link_code>", methods=["GET", "POST"])
@auto_commit_after_request
def claim_magic_link(magic_link_code: str) -> ResponseReturnValue:
    magic_link = interfaces.magic_link.get_magic_link(code=magic_link_code)
    if not magic_link or not magic_link.usable:
        return redirect(url_for("auth.request_a_link_to_sign_in"))

    form = ClaimMagicLinkForm()
    if form.validate_on_submit():
        interfaces.magic_link.claim_magic_link(magic_link=magic_link)
        if not login_user(magic_link.user):
            abort(400)

        return redirect(sanitise_redirect_url(magic_link.redirect_to_path))

    return render_template("common/auth/claim_magic_link.html", form=form, magic_link=magic_link)


@auth_blueprint.get("/sign-out")
def sign_out() -> ResponseReturnValue:
    logout_user()

    return redirect(url_for("index"))
