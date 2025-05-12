from typing import cast

from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user
from pydantic import UUID4
from werkzeug import Response
from wtforms.fields.core import Field

from app.common.auth.decorators import mhclg_login_required
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_collection_schema,
    create_form,
    create_section,
    get_collection_schema,
    get_form_by_id,
    get_section_by_id,
    move_form_down,
    move_form_up,
    move_section_down,
    move_section_up,
    update_collection_schema,
    update_section,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import User
from app.extensions import auto_commit_after_request
from app.platform.forms import CollectionForm, FormForm, GrantForm, SectionForm

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
    return render_template("platform/developers/list_collections.html", grant=grant)


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
    return render_template("platform/developers/add_collection.html", grant=grant, form=form)


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def manage_collection(grant_id: UUID4, collection_id: UUID4) -> ResponseReturnValue:
    collection = get_collection_schema(collection_id)
    return render_template("platform/developers/manage_collection.html", grant=collection.grant, collection=collection)


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


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/add", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def add_section(grant_id: UUID4, collection_id: UUID4) -> ResponseReturnValue:
    collection = get_collection_schema(collection_id)
    form = SectionForm(collection_id=collection_id)
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_section(
                title=form.title.data,
                collection_schema=collection,
            )
            return redirect(url_for("platform.list_sections", grant_id=grant_id, collection_id=collection_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]
    return render_template(
        "platform/developers/add_section.html", grant=collection.grant, collection=collection, form=form
    )


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def list_sections(
    grant_id: UUID4,
    collection_id: UUID4,
) -> ResponseReturnValue:
    collection_schema = get_collection_schema(collection_id)
    return render_template(
        "platform/developers/list_sections.html", grant=collection_schema.grant, collection=collection_schema
    )


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/move/<string:direction>",
    methods=["GET"],
)
@mhclg_login_required
@auto_commit_after_request
def move_section(grant_id: UUID4, collection_id: UUID4, section_id: UUID4, direction: str) -> ResponseReturnValue:
    section = get_section_by_id(section_id)

    if direction == "up":
        move_section_up(section)
    elif direction == "down":
        move_section_down(section)

    return redirect(url_for("platform.list_sections", grant_id=grant_id, collection_id=collection_id))


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/manage",
    methods=["GET"],
)
@mhclg_login_required
@auto_commit_after_request
def manage_section(
    grant_id: UUID4,
    collection_id: UUID4,
    section_id: UUID4,
) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    return render_template(
        "platform/developers/manage_section.html",
        grant=section.collection_schema.grant,
        collection=section.collection_schema,
        section=section,
    )


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/move/<string:direction>",
    methods=["GET"],
)
@mhclg_login_required
@auto_commit_after_request
def move_form(
    grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4, direction: str
) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    if direction == "up":
        move_form_up(form)
    elif direction == "down":
        move_form_down(form)

    return redirect(
        url_for("platform.manage_section", grant_id=grant_id, collection_id=collection_id, section_id=section_id)
    )


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/manage",
    methods=["GET"],
)
@mhclg_login_required
@auto_commit_after_request
def manage_form(grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    return render_template(
        "platform/developers/manage_form.html",
        grant=form.section.collection_schema.grant,
        section=form.section,
        collection=form.section.collection_schema,
        form=form,
        back_link_href=url_for(
            f"platform.{request.args.get('back_link')}",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
        ),
    )


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/edit",
    methods=["GET", "POST"],
)
@mhclg_login_required
@auto_commit_after_request
def edit_section(grant_id: UUID4, collection_id: UUID4, section_id: UUID4) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form = SectionForm(obj=section)
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            update_section(section=section, title=form.title.data)
            return redirect(
                url_for(
                    "platform.manage_section", grant_id=grant_id, collection_id=collection_id, section_id=section_id
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]

    return render_template(
        "platform/developers/edit_section.html",
        grant=section.collection_schema.grant,
        collection=section.collection_schema,
        section=section,
        form=form,
    )


@platform_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/add",
    methods=["GET", "POST"],
)
@mhclg_login_required
@auto_commit_after_request
def add_form(grant_id: UUID4, collection_id: UUID4, section_id: UUID4) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form_type = request.args.get("form_type", None)
    if not form_type:
        return render_template(
            "platform/developers/select_form_type.html",
            grant=section.collection_schema.grant,
            collection=section.collection_schema,
            section=section,
        )

    form = FormForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_form(title=form.title.data, section=section)
            return redirect(
                url_for(
                    "platform.manage_section", grant_id=grant_id, collection_id=collection_id, section_id=section_id
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.label.text} already in use")  # type:ignore[attr-defined]
    return render_template(
        "platform/developers/add_form.html",
        grant=section.collection_schema.grant,
        collection=section.collection_schema,
        section=section,
        form_type=form_type,
        form=form,
    )
