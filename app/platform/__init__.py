from flask import Blueprint, redirect, render_template, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug import Response

from app.common.data.interfaces.grants import add_grant, get_all_grants
from app.extensions import db
from app.platform.forms import GrantForm

# TODO do we call this platform
platform_blueprint = Blueprint(name="platform", import_name=__name__)


# TODO think about a naming convention for route handlers
@platform_blueprint.route("/grant", methods=["GET", "POST"])
def create_grant() -> str | Response:
    form = GrantForm()
    if form.validate_on_submit():
        with db.get_session() as session, session.begin():
            try:
                add_grant(name=form.name.data)  # type: ignore[arg-type]
                return redirect(url_for("platform.grant_list"))
            except IntegrityError:
                # Typing error on next line is because errors is defined as a tuple but at runtime is a list
                form.name.errors.append("Grant name already in use")  # type:ignore[attr-defined]
    return render_template("platform/grant.html", form=form)


@platform_blueprint.route("/grant_list", methods=["GET"])
def grant_list() -> str:
    grant_list = get_all_grants()
    return render_template("platform/grant_list.html", grant_list=grant_list)
