from flask import Blueprint, redirect, render_template, url_for
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError
from werkzeug import Response

from app.common.data.interfaces.grants import create_grant, get_all_grants, get_grant
from app.extensions import db
from app.platform.forms import GrantForm

# TODO do we call this platform
platform_blueprint = Blueprint(name="platform", import_name=__name__)


# TODO think about a naming convention for route handlers
@platform_blueprint.route("/grants/add", methods=["GET", "POST"])
def add_grant() -> str | Response:
    form = GrantForm()
    if form.validate_on_submit():
        with db.get_session() as session, session.begin():
            try:
                create_grant(name=form.name.data)  # type: ignore
                return redirect(url_for("platform.grant_list"))
            except IntegrityError:
                # Typing error on next line is because errors is defined as a tuple but at runtime is a list
                form.name.errors.append("Grant name already in use")  # type:ignore[attr-defined]
    return render_template("platform/grant.html", form=form)


@platform_blueprint.route("/grants", methods=["GET"])
def view_all_grants() -> str:
    grant_list = get_all_grants()
    return render_template("platform/grant_list.html", grant_list=grant_list)


@platform_blueprint.route("/grants/<grant_id>", methods=["GET"])
def view_grant(grant_id: UUID4) -> str:
    grant = get_grant(grant_id)
    return render_template("platform/grant_details.html", grant=grant)


@platform_blueprint.route("/grants/<grant_id>/settings", methods=["GET"])
def grant_settings(grant_id: UUID4) -> str:
    grant = get_grant(grant_id)
    return render_template("platform/grant_settings.html", grant=grant)
