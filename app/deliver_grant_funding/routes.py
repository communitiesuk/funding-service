from flask import Blueprint, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from pydantic import UUID4
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.auth.decorators import mhclg_login_required
from app.common.data import interfaces
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.deliver_grant_funding.forms import (
    GrantForm,
)
from app.extensions import auto_commit_after_request

deliver_grant_funding_blueprint = Blueprint(name="deliver_grant_funding", import_name=__name__)


@deliver_grant_funding_blueprint.route("/grants/set-up", methods=["GET", "POST"])
@mhclg_login_required
@auto_commit_after_request
def create_grant() -> ResponseReturnValue:
    form = GrantForm()
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            interfaces.grants.create_grant(name=form.name.data)
            return redirect(url_for("deliver_grant_funding.list_grants"))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("deliver_grant_funding/grant_create.html", form=form)


@deliver_grant_funding_blueprint.route("/grants", methods=["GET"])
@mhclg_login_required
def list_grants() -> str:
    grants = interfaces.grants.get_all_grants()
    return render_template("deliver_grant_funding/grant_list.html", grants=grants)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
@mhclg_login_required
def view_grant(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_view.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/settings", methods=["GET"])
@mhclg_login_required
def grant_settings(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/grant_settings.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/change-name", methods=["GET", "POST"])
@mhclg_login_required
@auto_commit_after_request
def grant_change_name(grant_id: UUID4) -> str | Response:
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
