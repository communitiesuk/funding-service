from flask import Blueprint, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.forms import SignInForm

auth_blueprint = Blueprint(
    "auth",
    __name__,
    url_prefix="/",
)


@auth_blueprint.route("/sign-in", methods=["GET", "POST"])
def sign_in() -> ResponseReturnValue:
    form = SignInForm()
    if form.validate_on_submit():
        email = form.email_address.data

        # TODO: all session stuff will be revisited as part of FSPT-334
        session["email_address"] = email

        return redirect(url_for("auth.check_email"))

    return render_template("common/auth/sign_in.html", form=form)


@auth_blueprint.get("/check-your-email")
def check_email() -> ResponseReturnValue:
    if "email_address" not in session:
        return redirect(url_for("auth.sign_in"))

    email_address = session.get("email_address")
    return render_template("common/auth/check_email.html", email_address=email_address)
