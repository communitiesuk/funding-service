from typing import cast

from flask import Blueprint, abort, redirect, render_template, request, url_for
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
    create_question,
    create_section,
    get_collection_schema,
    get_form_by_id,
    get_question_by_id,
    get_section_by_id,
    move_form_down,
    move_form_up,
    move_question_down,
    move_question_up,
    move_section_down,
    move_section_up,
    update_collection_schema,
    update_form,
    update_question,
    update_section,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import QuestionDataType, User
from app.deliver_grant_funding.forms import (
    CollectionForm,
    FormForm,
    GrantForm,
    QuestionForm,
    QuestionTypeForm,
    SectionForm,
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


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/developers", methods=["GET"])
@mhclg_login_required
def grant_developers(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/developers/grant_developers.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/developers/collections", methods=["GET"])
@mhclg_login_required
def grant_developers_collections(grant_id: UUID4) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("deliver_grant_funding/developers/list_collections.html", grant=grant)


@deliver_grant_funding_blueprint.route("/grants/<uuid:grant_id>/developers/collections/set-up", methods=["GET", "POST"])
@mhclg_login_required
@auto_commit_after_request
def setup_collection(grant_id: UUID4) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = CollectionForm()
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            create_collection_schema(name=form.name.data, user=cast(User, current_user), grant=grant)
            return redirect(url_for("deliver_grant_funding.grant_developers_collections", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("deliver_grant_funding/developers/add_collection.html", grant=grant, form=form)


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def manage_collection(grant_id: UUID4, collection_id: UUID4) -> ResponseReturnValue:
    collection = get_collection_schema(collection_id)
    return render_template(
        "deliver_grant_funding/developers/manage_collection.html", grant=collection.grant, collection=collection
    )


@deliver_grant_funding_blueprint.route(
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
            return redirect(
                url_for("deliver_grant_funding.manage_collection", grant_id=grant_id, collection_id=collection_id)
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/developers/edit_collection.html",
        grant=collection.grant,
        collection=collection,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/add", methods=["GET", "POST"]
)
@mhclg_login_required
@auto_commit_after_request
def add_section(grant_id: UUID4, collection_id: UUID4) -> ResponseReturnValue:
    collection = get_collection_schema(collection_id)
    form = SectionForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_section(
                title=form.title.data,
                collection_schema=collection,
            )
            return redirect(
                url_for("deliver_grant_funding.list_sections", grant_id=grant_id, collection_id=collection_id)
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template(
        "deliver_grant_funding/developers/add_section.html", grant=collection.grant, collection=collection, form=form
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/", methods=["GET"]
)
@mhclg_login_required
def list_sections(
    grant_id: UUID4,
    collection_id: UUID4,
) -> ResponseReturnValue:
    collection_schema = get_collection_schema(collection_id)
    return render_template(
        "deliver_grant_funding/developers/list_sections.html",
        grant=collection_schema.grant,
        collection=collection_schema,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/move/<string:direction>",
    methods=["POST"],
)
@mhclg_login_required
@auto_commit_after_request
def move_section(grant_id: UUID4, collection_id: UUID4, section_id: UUID4, direction: str) -> ResponseReturnValue:
    section = get_section_by_id(section_id)

    if direction == "up":
        move_section_up(section)
    elif direction == "down":
        move_section_down(section)
    else:
        abort(400)

    return redirect(url_for("deliver_grant_funding.list_sections", grant_id=grant_id, collection_id=collection_id))


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/manage",
    methods=["GET"],
)
@mhclg_login_required
def manage_section(
    grant_id: UUID4,
    collection_id: UUID4,
    section_id: UUID4,
) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    return render_template(
        "deliver_grant_funding/developers/manage_section.html",
        grant=section.collection_schema.grant,
        collection=section.collection_schema,
        section=section,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/move/<string:direction>",
    methods=["POST"],
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
    else:
        abort(400)

    return redirect(
        url_for(
            "deliver_grant_funding.manage_section",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
        )
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/manage",
    methods=["GET"],
)
@mhclg_login_required
def manage_form(grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    return render_template(
        "deliver_grant_funding/developers/manage_form.html",
        grant=form.section.collection_schema.grant,
        section=form.section,
        collection=form.section.collection_schema,
        form=form,
        back_link_href=url_for(
            f"deliver_grant_funding.{request.args.get('back_link')}",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
        ),
    )


@deliver_grant_funding_blueprint.route(
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
                    "deliver_grant_funding.manage_section",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/developers/edit_section.html",
        grant=section.collection_schema.grant,
        collection=section.collection_schema,
        section=section,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
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
            "deliver_grant_funding/developers/select_form_type.html",
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
                    "deliver_grant_funding.manage_section",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template(
        "deliver_grant_funding/developers/add_form.html",
        grant=section.collection_schema.grant,
        collection=section.collection_schema,
        section=section,
        form_type=form_type,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/edit",
    methods=["GET", "POST"],
)
@mhclg_login_required
@auto_commit_after_request
def edit_form(grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = FormForm(obj=db_form)
    if wt_form.validate_on_submit():
        try:
            assert wt_form.title.data is not None
            update_form(form=db_form, title=wt_form.title.data)
            return redirect(
                url_for(
                    "deliver_grant_funding.manage_form",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                    back_link="manage_section",
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/developers/edit_form.html",
        grant=db_form.section.collection_schema.grant,
        collection=db_form.section.collection_schema,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add/choose-type",
    methods=["GET", "POST"],
)
@mhclg_login_required
def choose_question_type(
    grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4
) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))
    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data
        return redirect(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant_id,
                collection_id=collection_id,
                section_id=section_id,
                form_id=form_id,
                question_data_type=question_data_type,
            )
        )
    return render_template(
        "deliver_grant_funding/developers/choose_question_type.html",
        grant=db_form.section.collection_schema.grant,
        collection=db_form.section.collection_schema,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@mhclg_login_required
@auto_commit_after_request
def add_question(grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    question_data_type_arg = request.args.get("question_data_type", QuestionDataType.TEXT_SINGLE_LINE.name)
    question_data_type_enum = QuestionDataType.coerce(question_data_type_arg)

    wt_form = QuestionForm()
    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            create_question(
                form=form,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                data_type=question_data_type_enum,
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.manage_form",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                    back_link="manage_section",
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/developers/add_question.html",
        grant=form.section.collection_schema.grant,
        collection=form.section.collection_schema,
        section=form.section,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/move/<string:direction>",
    methods=["POST"],
)
@mhclg_login_required
@auto_commit_after_request
def move_question(
    grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4, question_id: UUID4, direction: str
) -> ResponseReturnValue:
    question = get_question_by_id(question_id=question_id)

    if direction == "up":
        move_question_up(question)
    elif direction == "down":
        move_question_down(question)
    else:
        abort(400)

    return redirect(
        url_for(
            "deliver_grant_funding.manage_form",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
            form_id=form_id,
            back_link="manage_section",
        )
    )


@deliver_grant_funding_blueprint.route(
    "/grants/<uuid:grant_id>/developers/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/edit",
    methods=["GET", "POST"],
)
@mhclg_login_required
@auto_commit_after_request
def edit_question(
    grant_id: UUID4, collection_id: UUID4, section_id: UUID4, form_id: UUID4, question_id: UUID4
) -> ResponseReturnValue:
    question = get_question_by_id(question_id=question_id)
    wt_form = QuestionForm(obj=question)
    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            update_question(question=question, text=wt_form.text.data, hint=wt_form.hint.data, name=wt_form.name.data)
            return redirect(
                url_for(
                    "deliver_grant_funding.manage_form",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                    back_link="manage_section",
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "deliver_grant_funding/developers/edit_question.html",
        grant=question.form.section.collection_schema.grant,
        collection=question.form.section.collection_schema,
        section=question.form.section,
        db_form=question.form,
        question=question,
        form=wt_form,
    )
