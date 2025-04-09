from flask import Blueprint, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from pydantic import UUID4
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.data import interfaces
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.extensions import auto_commit_after_request
from app.platform.forms import GrantForm

platform_blueprint = Blueprint(name="platform", import_name=__name__)


@platform_blueprint.route("/grants/set-up", methods=["GET", "POST"])
@auto_commit_after_request
def create_grant() -> ResponseReturnValue:
    form = GrantForm()
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            interfaces.grants.create_grant(name=form.name.data)
            return redirect(url_for("platform.list_grants"))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]
    return render_template("platform/grant_create.html", form=form)


@platform_blueprint.route("/grants", methods=["GET"])
def list_grants() -> str:
    grants = interfaces.grants.get_all_grants()
    return render_template("platform/grant_list.html", grants=grants)


@platform_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
def view_grant(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("platform/grant_view.html", grant=grant)


@platform_blueprint.route("/grants/<uuid:grant_id>/settings", methods=["GET"])
def grant_settings(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("platform/grant_settings.html", grant=grant)


@platform_blueprint.route("/grants/<uuid:grant_id>/change-name", methods=["GET", "POST"])
@auto_commit_after_request
def grant_change_name(grant_id: UUID4) -> str | Response:
    grant = interfaces.grants.get_grant(grant_id)
    form = GrantForm(obj=grant)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            interfaces.grants.update_grant(grant=grant, name=form.name.data)
            return redirect(url_for("platform.grant_settings", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]
    return render_template("platform/settings/grant_change_name.html", form=form, grant=grant)
