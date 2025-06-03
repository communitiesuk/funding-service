from enum import StrEnum
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from wtforms import Field
from wtforms.validators import DataRequired
from wtforms.validators import Optional as WTFOptional

from app.common.auth.decorators import platform_admin_role_required
from app.common.collections.forms import build_question_form
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_collection,
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
from app.common.data.interfaces.temporary import delete_collections_created_by_user
from app.common.data.types import CollectionStatusEnum, QuestionDataType
from app.common.helpers.collections import CollectionHelper
from app.deliver_grant_funding.forms import (
    FormForm,
    QuestionForm,
    QuestionTypeForm,
    SchemaForm,
    SectionForm,
)
from app.developers.forms import CheckYourAnswersForm, PreviewCollectionForm
from app.extensions import auto_commit_after_request

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form, Question

developers_blueprint = Blueprint(name="developers", import_name=__name__, url_prefix="/developers")


@developers_blueprint.context_processor
def inject_variables() -> dict[str, Any]:
    return dict(show_watermark=True)


@developers_blueprint.route("/grants/<uuid:grant_id>", methods=["GET"])
@platform_admin_role_required
def grant_developers(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("developers/grant_developers.html", grant=grant)


@developers_blueprint.route("/grants/<uuid:grant_id>/schemas", methods=["GET"])
@platform_admin_role_required
def grant_developers_schemas(grant_id: UUID) -> str:
    grant = interfaces.grants.get_grant(grant_id)
    return render_template("developers/list_schemas.html", grant=grant)


@developers_blueprint.route("/grants/<uuid:grant_id>/schemas/set-up", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def setup_schema(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = SchemaForm()
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            user = interfaces.user.get_current_user()
            create_collection_schema(name=form.name.data, user=user, grant=grant)
            return redirect(url_for("developers.grant_developers_schemas", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("developers/add_schema.html", grant=grant, form=form)


@developers_blueprint.route("/grants/<uuid:grant_id>/schemas/<uuid:schema_id>", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def manage_schema(grant_id: UUID, schema_id: UUID) -> ResponseReturnValue:
    schema = get_collection_schema(schema_id)  # TODO: handle collection versioning; this just grabs latest.
    form = PreviewCollectionForm()
    if form.validate_on_submit():
        user = interfaces.user.get_current_user()
        delete_collections_created_by_user(grant_id=schema.grant_id, created_by_id=user.id)
        collection = create_collection(schema=schema, created_by=user)
        return redirect(url_for("developers.collection_tasklist", collection_id=collection.id))

    return render_template("developers/manage_schema.html", grant=schema.grant, schema=schema, form=form)


@developers_blueprint.route("/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/edit", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def edit_schema(grant_id: UUID, schema_id: UUID) -> ResponseReturnValue:
    schema = get_collection_schema(schema_id)  # TODO: handle collection versioning; this just grabs latest.
    form = SchemaForm(obj=schema)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            update_collection_schema(name=form.name.data, schema=schema)
            return redirect(url_for("developers.manage_schema", grant_id=grant_id, schema_id=schema_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_schema.html",
        grant=schema.grant,
        schema=schema,
        form=form,
    )


@developers_blueprint.route("/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/add", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def add_section(grant_id: UUID, schema_id: UUID) -> ResponseReturnValue:
    collection = get_collection_schema(schema_id)  # TODO: handle collection versioning; this just grabs latest.
    form = SectionForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_section(
                title=form.title.data,
                schema=collection,
            )
            return redirect(url_for("developers.list_sections", grant_id=grant_id, schema_id=schema_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("developers/add_section.html", grant=collection.grant, schema=collection, form=form)


@developers_blueprint.route("/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/", methods=["GET"])
@platform_admin_role_required
def list_sections(
    grant_id: UUID,
    schema_id: UUID,
) -> ResponseReturnValue:
    collection_schema = get_collection_schema(schema_id)
    return render_template(
        "developers/list_sections.html",
        grant=collection_schema.grant,
        schema=collection_schema,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/move/<string:direction>",
    methods=["POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def move_section(grant_id: UUID, schema_id: UUID, section_id: UUID, direction: str) -> ResponseReturnValue:
    section = get_section_by_id(section_id)

    if direction == "up":
        move_section_up(section)
    elif direction == "down":
        move_section_down(section)
    else:
        abort(400)

    return redirect(url_for("developers.list_sections", grant_id=grant_id, schema_id=schema_id))


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/manage",
    methods=["GET"],
)
@platform_admin_role_required
def manage_section(
    grant_id: UUID,
    schema_id: UUID,
    section_id: UUID,
) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    return render_template(
        "developers/manage_section.html",
        grant=section.collection_schema.grant,
        schema=section.collection_schema,
        section=section,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/move/<string:direction>",
    methods=["POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def move_form(grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID, direction: str) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    if direction == "up":
        move_form_up(form)
    elif direction == "down":
        move_form_down(form)
    else:
        abort(400)

    return redirect(
        url_for(
            "developers.manage_section",
            grant_id=grant_id,
            schema_id=schema_id,
            section_id=section_id,
        )
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/manage",
    methods=["GET"],
)
@platform_admin_role_required
def manage_form(grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    return render_template(
        "developers/manage_form.html",
        grant=form.section.collection_schema.grant,
        section=form.section,
        schema=form.section.collection_schema,
        form=form,
        back_link_href=url_for(
            f"developers.{request.args.get('back_link')}",
            grant_id=grant_id,
            schema_id=schema_id,
            section_id=section_id,
        ),
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/edit",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def edit_section(grant_id: UUID, schema_id: UUID, section_id: UUID) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form = SectionForm(obj=section)
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            update_section(section=section, title=form.title.data)
            return redirect(
                url_for(
                    "developers.manage_section",
                    grant_id=grant_id,
                    schema_id=schema_id,
                    section_id=section_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_section.html",
        grant=section.collection_schema.grant,
        schema=section.collection_schema,
        section=section,
        form=form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/add",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def add_form(grant_id: UUID, schema_id: UUID, section_id: UUID) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form_type = request.args.get("form_type", None)
    if not form_type:
        return render_template(
            "developers/select_form_type.html",
            grant=section.collection_schema.grant,
            schema=section.collection_schema,
            section=section,
        )

    form = FormForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_form(title=form.title.data, section=section)
            return redirect(
                url_for(
                    "developers.manage_section",
                    grant_id=grant_id,
                    schema_id=schema_id,
                    section_id=section_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template(
        "developers/add_form.html",
        grant=section.collection_schema.grant,
        schema=section.collection_schema,
        section=section,
        form_type=form_type,
        form=form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/edit",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def edit_form(grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = FormForm(obj=db_form)
    if wt_form.validate_on_submit():
        try:
            assert wt_form.title.data is not None
            update_form(form=db_form, title=wt_form.title.data)
            return redirect(
                url_for(
                    "developers.manage_form",
                    grant_id=grant_id,
                    schema_id=schema_id,
                    section_id=section_id,
                    form_id=form_id,
                    back_link="manage_section",
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_form.html",
        grant=db_form.section.collection_schema.grant,
        schema=db_form.section.collection_schema,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add/choose-type",
    methods=["GET", "POST"],
)
@platform_admin_role_required
def choose_question_type(grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))
    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data
        return redirect(
            url_for(
                "developers.add_question",
                grant_id=grant_id,
                schema_id=schema_id,
                section_id=section_id,
                form_id=form_id,
                question_data_type=question_data_type,
            )
        )
    return render_template(
        "developers/choose_question_type.html",
        grant=db_form.section.collection_schema.grant,
        schema=db_form.section.collection_schema,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def add_question(grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
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
                    "developers.manage_form",
                    grant_id=grant_id,
                    schema_id=schema_id,
                    section_id=section_id,
                    form_id=form_id,
                    back_link="manage_section",
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/add_question.html",
        grant=form.section.collection_schema.grant,
        schema=form.section.collection_schema,
        section=form.section,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/move/<string:direction>",
    methods=["POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def move_question(
    grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID, question_id: UUID, direction: str
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
            "developers.manage_form",
            grant_id=grant_id,
            schema_id=schema_id,
            section_id=section_id,
            form_id=form_id,
            back_link="manage_section",
        )
    )


@developers_blueprint.route(
    "/grants/<uuid:grant_id>/schemas/<uuid:schema_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/edit",
    methods=["GET", "POST"],
)
@platform_admin_role_required
@auto_commit_after_request
def edit_question(
    grant_id: UUID, schema_id: UUID, section_id: UUID, form_id: UUID, question_id: UUID
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
                    "developers.manage_form",
                    grant_id=grant_id,
                    schema_id=schema_id,
                    section_id=section_id,
                    form_id=form_id,
                    back_link="manage_section",
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/edit_question.html",
        grant=question.form.section.collection_schema.grant,
        schema=question.form.section.collection_schema,
        section=question.form.section,
        db_form=question.form,
        question=question,
        form=wt_form,
    )


class FormRunnerSourceEnum(StrEnum):
    QUESTION = "question"
    TASKLIST = "tasklist"
    CHECK_YOUR_ANSWERS = "check-your-answers"


def _get_form_runner_link_from_source(
    source: str | None,
    collection: Optional["Collection"] = None,
    form: Optional["Form"] = None,
    question: Optional["Question"] = None,
) -> str | None:
    if not source:
        return None

    if source == FormRunnerSourceEnum.QUESTION and collection and question:
        return url_for("developers.ask_a_question", collection_id=collection.id, question_id=question.id)
    elif source == FormRunnerSourceEnum.TASKLIST and collection:
        return url_for("developers.collection_tasklist", collection_id=collection.id)
    elif source == FormRunnerSourceEnum.CHECK_YOUR_ANSWERS and collection and form:
        return url_for("developers.check_your_answers", collection_id=collection.id, form_id=form.id)

    return None


@developers_blueprint.route("/collections/<uuid:collection_id>", methods=["GET"])
@platform_admin_role_required
def collection_tasklist(collection_id: UUID) -> ResponseReturnValue:
    collection_helper = CollectionHelper.load(collection_id)
    return render_template(
        "developers/collection_tasklist.html",
        collection_helper=collection_helper,
        statuses=CollectionStatusEnum,
        back_link_source_enum=FormRunnerSourceEnum,
    )


@developers_blueprint.route("/collections/<uuid:collection_id>/<uuid:question_id>", methods=["GET", "POST"])
@platform_admin_role_required
@auto_commit_after_request
def ask_a_question(collection_id: UUID, question_id: UUID) -> ResponseReturnValue:
    collection_helper = CollectionHelper.load(collection_id)
    question = collection_helper.get_question(question_id)
    answer = collection_helper.get_answer_for_question(question.id)

    # this method should work as long as data types are a single field and may
    # need to be revised if we have compound data types
    form = build_question_form(question)(question=answer.root if answer else None)

    if form.validate_on_submit():
        collection_helper.submit_answer_for_question(question.id, form)

        if request.args.get("source") == FormRunnerSourceEnum.CHECK_YOUR_ANSWERS:
            return redirect(
                url_for("developers.check_your_answers", collection_id=collection_id, form_id=question.form_id)
            )

        next_question = collection_helper.get_next_question(current_question_id=question_id)
        if next_question:
            return redirect(
                url_for("developers.ask_a_question", collection_id=collection_id, question_id=next_question.id)
            )

        return redirect(url_for("developers.check_your_answers", collection_id=collection_id, form_id=question.form_id))

    previous_question = collection_helper.get_previous_question(current_question_id=question_id)
    back_link_from_context = _get_form_runner_link_from_source(
        source=request.args.get("source"),
        collection=collection_helper.collection,
        form=question.form,
        question=question,
    )
    back_link = (
        back_link_from_context
        if back_link_from_context
        else url_for(
            "developers.ask_a_question", collection_id=collection_helper.collection.id, question_id=previous_question.id
        )
        if previous_question
        else url_for("developers.collection_tasklist", collection_id=collection_helper.collection.id)
    )
    return render_template(
        "developers/ask_a_question.html",
        back_link=back_link,
        collection_helper=collection_helper,
        form=form,
        question=question,
        question_types=QuestionDataType,
        back_link_source_enum=FormRunnerSourceEnum,
    )


@developers_blueprint.route(
    "/collections/<uuid:collection_id>/check-yours-answers/<uuid:form_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@platform_admin_role_required
def check_your_answers(collection_id: UUID, form_id: UUID) -> ResponseReturnValue:
    collection_helper = CollectionHelper.load(collection_id)
    schema_form = collection_helper.get_form(form_id)

    form = CheckYourAnswersForm(
        section_completed="yes" if collection_helper.status == CollectionStatusEnum.COMPLETED else None
    )
    previous_question = collection_helper.get_last_question_for_form(schema_form)
    assert previous_question

    back_link_from_context = _get_form_runner_link_from_source(
        source=request.args.get("source"), collection=collection_helper.collection, form=schema_form
    )
    back_link = (
        back_link_from_context
        if back_link_from_context
        else url_for(
            "developers.ask_a_question", collection_id=collection_helper.collection.id, question_id=previous_question.id
        )
    )

    all_questions_answered, _ = collection_helper.get_all_questions_answered_for_form(schema_form)
    extra_validators = {
        "section_completed": [
            DataRequired("Select if you have you completed this section") if all_questions_answered else WTFOptional()
        ]
    }

    if form.validate_on_submit(extra_validators=extra_validators):
        try:
            collection_helper.mark_form_as_complete(
                form=schema_form, user=current_user, is_complete=form.section_completed.data == "yes"
            )
            return redirect(url_for("developers.collection_tasklist", collection_id=collection_helper.id))
        except ValueError:
            form.section_completed.errors.append(  # type:ignore[attr-defined]
                "You must complete all questions before marking this section as complete"
            )

    return render_template(
        "developers/check_your_answers.html",
        back_link=back_link,
        collection_helper=collection_helper,
        schema_form=schema_form,
        form=form,
        back_link_source_enum=FormRunnerSourceEnum,
    )


@developers_blueprint.route("/schemas/<uuid:schema_id>/collections", methods=["GET"])
@platform_admin_role_required
def list_collections_for_schema(schema_id: UUID) -> ResponseReturnValue:
    schema = interfaces.collections.get_collection_schema(schema_id, with_full_schema=True)

    collections = [CollectionHelper(collection) for collection in schema.collections]

    return render_template(
        "developers/list_collections.html",
        back_link=url_for("developers.manage_schema", schema_id=schema.id, grant_id=schema.grant.id),
        grant=schema.grant,
        schema=schema,
        collections=collections,
        statuses=CollectionStatusEnum,
    )


@developers_blueprint.route("/collection/<uuid:collection_id>", methods=["GET"])
@platform_admin_role_required
def manage_collection(collection_id: UUID) -> ResponseReturnValue:
    collection_helper = CollectionHelper.load(collection_id)

    return render_template(
        "developers/manage_collection.html",
        back_link=url_for("developers.list_collections_for_schema", schema_id=collection_helper.schema.id),
        collection_helper=collection_helper,
        grant=collection_helper.schema.grant,
        schema=collection_helper.schema,
        statuses=CollectionStatusEnum,
    )
