from typing import cast

from flask import Blueprint, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user
from pydantic import UUID4
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.auth.decorators import mhclg_login_required
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_collection_schema,
    get_collection_schema,
    update_collection_schema,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import User
from app.extensions import auto_commit_after_request
from app.platform.forms import CollectionForm, GrantForm

platform_blueprint = Blueprint(name="platform", import_name=__name__)


@platform_blueprint.route("/grants/set-up", methods=["GET", "POST"])
@mhclg_login_required
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
@mhclg_login_required
def list_grants() -> str:
    grants = interfaces.grants.get_all_grants()
    return render_template("platform/grant_list.html", grants=grants)


@platform_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
@mhclg_login_required
def view_grant(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("platform/grant_view.html", grant=grant)


@platform_blueprint.route("/grants/<uuid:grant_id>/settings", methods=["GET"])
@mhclg_login_required
def grant_settings(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("platform/grant_settings.html", grant=grant)


@platform_blueprint.route("/grants/<uuid:grant_id>/change-name", methods=["GET", "POST"])
@mhclg_login_required
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


@platform_blueprint.route("/grants/<uuid:grant_id>/developers", methods=["GET"])
@mhclg_login_required
def grant_developers(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("platform/developers/grant_developers.html", grant=grant)


@platform_blueprint.route("/grants/<uuid:grant_id>/developers/collections", methods=["GET"])
@mhclg_login_required
def grant_developers_collections(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("platform/developers/collections_list.html", grant=grant)


@platform_blueprint.route("/grants/<uuid:grant_id>/developers/collections/set-up", methods=["GET", "POST"])
@mhclg_login_required
@auto_commit_after_request
def setup_collection(grant_id: UUID4) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = CollectionForm(grant_id=grant.id)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            create_collection_schema(name=form.name.data, user=cast(User, current_user), grant=grant)
            return redirect(url_for("platform.grant_developers_collections", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]
    return render_template("platform/developers/create_collection.html", grant=grant, form=form)


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def manage_collection(grant_id: UUID4, collection_id: UUID4) -> ResponseReturnValue:
    collection = get_collection_schema(collection_id)
    return render_template("platform/developers/collection_details.html", grant=collection.grant, collection=collection)


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/edit", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def edit_collection(grant_id: UUID4, collection_id: UUID4) -> ResponseReturnValue:
    collection = get_collection_schema(collection_id)
    form = CollectionForm(obj=collection)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            update_collection_schema(name=form.name.data, collection=collection)
            return redirect(url_for("platform.manage_collection", grant_id=grant_id, collection_id=collection_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]

    return render_template(
        "platform/developers/edit_collection.html", grant=collection.grant, collection=collection, form=form
    )
