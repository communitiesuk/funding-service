import io
import uuid
from typing import TYPE_CHECKING
from uuid import UUID

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import NoResultFound
from wtforms import Field

from app.common.auth.decorators import is_platform_admin
from app.common.collections.runner import DGFFormRunner
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    DataSourceItemReferenceDependencyException,
    DependencyOrderException,
    create_collection,
    create_form,
    create_question,
    create_section,
    get_collection,
    get_form_by_id,
    get_question_by_id,
    get_section_by_id,
    move_form_down,
    move_form_up,
    move_question_down,
    move_question_up,
    move_section_down,
    move_section_up,
    raise_if_question_has_any_dependencies,
    remove_question_expression,
    update_collection,
    update_form,
    update_question,
    update_section,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.temporary import (
    delete_collection,
    delete_form,
    delete_grant,
    delete_question,
    delete_section,
)
from app.common.data.types import (
    CollectionType,
    ExpressionType,
    FormRunnerState,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.expressions.forms import build_managed_expression_form
from app.common.expressions.registry import get_managed_validators_by_data_type
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import CollectionHelper, SubmissionHelper
from app.deliver_grant_funding.forms import (
    CollectionForm,
    FormForm,
    QuestionForm,
    QuestionTypeForm,
    SectionForm,
)
from app.developers.forms import (
    BecomeGrantTeamMemberForm,
    ConditionSelectQuestionForm,
    ConfirmDeletionForm,
)
from app.developers.helpers import start_testing_submission
from app.extensions import auto_commit_after_request
from app.types import FlashMessageType

if TYPE_CHECKING:
    pass


developers_deliver_blueprint = Blueprint("deliver", __name__, url_prefix="/deliver")


@developers_deliver_blueprint.route("/grants/<uuid:grant_id>", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def grant_developers(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    confirm_deletion_form = ConfirmDeletionForm()
    become_grant_team_member_form = BecomeGrantTeamMemberForm()
    if (
        "delete_grant" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_grant(grant_id=grant.id)
        return redirect(url_for("deliver_grant_funding.list_grants"))

    if become_grant_team_member_form.validate_on_submit():
        interfaces.user.remove_platform_admin_role_from_user(interfaces.user.get_current_user())
        interfaces.user.set_grant_team_role_for_user(interfaces.user.get_current_user(), grant, RoleEnum.MEMBER)
        return redirect(url_for("deliver_grant_funding.grant_details", grant_id=grant.id))

    return render_template(
        "developers/deliver/grant_developers.html",
        grant=grant,
        confirm_deletion_form=confirm_deletion_form,
        become_grant_team_member_form=become_grant_team_member_form,
        delete_grant="delete_grant" in request.args,
    )


@developers_deliver_blueprint.route("/grants/<uuid:grant_id>/collections/set-up", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def setup_collection(grant_id: UUID) -> ResponseReturnValue:
    grant = interfaces.grants.get_grant(grant_id)
    form = CollectionForm()
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            user = interfaces.user.get_current_user()
            create_collection(name=form.name.data, user=user, grant=grant, type_=CollectionType.MONITORING_REPORT)
            return redirect(url_for("developers.deliver.grant_developers", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template("developers/deliver/add_collection.html", grant=grant, form=form)


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/tasks", methods=["GET", "POST"]
)
@is_platform_admin
@auto_commit_after_request
def manage_collection_tasks(grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id)  # TODO: handle collection versioning; this just grabs latest.
    form = GenericSubmitForm()
    confirm_deletion_form = ConfirmDeletionForm()
    try:
        section_id = request.args.get("delete_section")
        section = get_section_by_id(uuid.UUID(section_id))
    except (TypeError, NoResultFound):
        section = None
    if section and confirm_deletion_form.validate_on_submit() and confirm_deletion_form.confirm_deletion.data:
        delete_section(section)
        # TODO: Flash message for deletion?
        return redirect(
            url_for("developers.deliver.manage_collection_tasks", grant_id=grant_id, collection_id=collection_id)
        )

    if form.validate_on_submit() and form.submit.data:
        return start_testing_submission(collection)

    return render_template(
        "developers/deliver/manage_collection_tasks.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        confirm_deletion_form=confirm_deletion_form,
        delete_section="delete_section" in request.args and section and section.title,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/edit", methods=["GET", "POST"]
)
@is_platform_admin
@auto_commit_after_request
def manage_collection(grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id)  # TODO: handle collection versioning; this just grabs latest.

    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_collection(collection.id)
        # TODO: Flash message for deletion?
        return redirect(url_for("developers.deliver.grant_developers", grant_id=grant_id, collection_id=collection_id))

    form = CollectionForm(obj=collection)
    if form.validate_on_submit():
        try:
            assert form.name.data is not None
            update_collection(name=form.name.data, collection=collection)
            return redirect(url_for("developers.deliver.grant_developers", grant_id=grant_id))
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/deliver/manage_collection.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        confirm_deletion_form=confirm_deletion_form,
        delete_collection="delete" in request.args and collection,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/add", methods=["GET", "POST"]
)
@is_platform_admin
@auto_commit_after_request
def add_section(grant_id: UUID, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id)  # TODO: handle collection versioning; this just grabs latest.
    form = SectionForm()
    if form.validate_on_submit():
        assert form.title.data is not None

        try:
            if not collection.has_non_default_sections:
                # 'Create' the first section by renaming the default section
                update_section(collection.sections[0], title=form.title.data)
            else:
                create_section(
                    title=form.title.data,
                    collection=collection,
                )
            return redirect(
                url_for("developers.deliver.manage_collection_tasks", grant_id=grant_id, collection_id=collection_id)
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template(
        "developers/deliver/add_section.html", grant=collection.grant, collection=collection, form=form
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/", methods=["GET"]
)
@is_platform_admin
def list_sections(
    grant_id: UUID,
    collection_id: UUID,
) -> ResponseReturnValue:
    collection = get_collection(collection_id)
    return render_template(
        "developers/deliver/list_sections.html",
        grant=collection.grant,
        collection=collection,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/move/<string:direction>",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def move_section(grant_id: UUID, collection_id: UUID, section_id: UUID, direction: str) -> ResponseReturnValue:
    section = get_section_by_id(section_id)

    if direction == "up":
        move_section_up(section)
    elif direction == "down":
        move_section_down(section)
    else:
        return abort(400)

    return redirect(
        url_for("developers.deliver.manage_collection_tasks", grant_id=grant_id, collection_id=collection_id)
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/move/<string:direction>",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def move_form(
    grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID, direction: str
) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    if direction == "up":
        move_form_up(form)
    elif direction == "down":
        move_form_down(form)
    else:
        return abort(400)

    return redirect(
        url_for(
            "developers.deliver.manage_collection_tasks",
            grant_id=grant_id,
            collection_id=collection_id,
        )
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def manage_form_questions(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id, with_all_questions=True)

    form = GenericSubmitForm()
    if form.validate_on_submit() and form.submit.data:
        return start_testing_submission(db_form.section.collection, form=db_form)

    return render_template(
        "developers/deliver/manage_form_questions.html",
        grant=db_form.section.collection.grant,
        section=db_form.section,
        collection=db_form.section.collection,
        db_form=db_form,
        form=form,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/manage",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def manage_section(grant_id: UUID, collection_id: UUID, section_id: UUID) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form = SectionForm(obj=section)

    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        delete_section(section)
        # TODO: Flash message for deletion?
        return redirect(
            url_for("developers.deliver.manage_collection_tasks", grant_id=grant_id, collection_id=collection_id)
        )

    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            update_section(section=section, title=form.title.data)
            return redirect(
                url_for(
                    "developers.deliver.manage_collection_tasks",
                    grant_id=grant_id,
                    collection_id=collection_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/deliver/manage_section.html",
        grant=section.collection.grant,
        collection=section.collection,
        section=section,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


# TODO: having this method do both selecting the type and adding the form feels like too much
@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/add",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def add_form(grant_id: UUID, collection_id: UUID, section_id: UUID) -> ResponseReturnValue:
    section = get_section_by_id(section_id)
    form_type = request.args.get("form_type", None)
    if not form_type:
        return render_template(
            "developers/deliver/select_form_type.html",
            grant=section.collection.grant,
            collection=section.collection,
            section=section,
        )

    form = FormForm()
    if form.validate_on_submit():
        try:
            assert form.title.data is not None
            create_form(title=form.title.data, section=section)
            return redirect(
                url_for("developers.deliver.manage_collection_tasks", grant_id=grant_id, collection_id=collection_id)
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
    return render_template(
        "developers/deliver/add_form.html",
        grant=section.collection.grant,
        collection=section.collection,
        section=section,
        form_type=form_type,
        form=form,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/manage",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def manage_form(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = FormForm(obj=db_form)

    delete_wt_form = ConfirmDeletionForm()
    if "delete" in request.args and delete_wt_form.validate_on_submit() and delete_wt_form.confirm_deletion.data:
        delete_form(db_form)
        return redirect(
            url_for("developers.deliver.manage_collection_tasks", grant_id=grant_id, collection_id=collection_id)
        )

    if wt_form.validate_on_submit():
        try:
            assert wt_form.title.data is not None
            update_form(form=db_form, title=wt_form.title.data, section_id=wt_form.section_id.data)
            return redirect(
                url_for(
                    "developers.deliver.manage_collection_tasks",
                    grant_id=grant_id,
                    collection_id=collection_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/deliver/manage_form.html",
        grant=db_form.section.collection.grant,
        collection=db_form.section.collection,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
        delete_form="delete" in request.args and delete_wt_form,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add/choose-type",
    methods=["GET", "POST"],
)
@is_platform_admin
def choose_question_type(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))
    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data
        return redirect(
            url_for(
                "developers.deliver.add_question",
                grant_id=grant_id,
                collection_id=collection_id,
                section_id=section_id,
                form_id=form_id,
                question_data_type=question_data_type,
            )
        )
    return render_template(
        "developers/deliver/choose_question_type.html",
        grant=db_form.section.collection.grant,
        collection=db_form.section.collection,
        section=db_form.section,
        db_form=db_form,
        form=wt_form,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def add_question(grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    question_data_type_arg = request.args.get("question_data_type", QuestionDataType.TEXT_SINGLE_LINE.name)
    question_data_type_enum = QuestionDataType.coerce(question_data_type_arg)

    wt_form = QuestionForm(question_type=question_data_type_enum)
    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None

            question = create_question(
                form=form,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                data_type=question_data_type_enum,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions(
                    last_data_source_item_is_distinct_from_others=wt_form.separate_option_if_no_items_match.data
                ),
            )
            flash("Question created", FlashMessageType.QUESTION_CREATED)
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                    question_id=question.id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]

    return render_template(
        "developers/deliver/add_question.html",
        grant=form.section.collection.grant,
        collection=form.section.collection,
        section=form.section,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/move/<string:direction>",
    methods=["POST"],
)
@is_platform_admin
@auto_commit_after_request
def move_question(
    grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID, question_id: UUID, direction: str
) -> ResponseReturnValue:
    question = get_question_by_id(question_id=question_id)

    if direction not in ["up", "down"]:
        return abort(400)

    try:
        if direction == "up":
            move_question_up(question)
        elif direction == "down":
            move_question_down(question)
    except DependencyOrderException as e:
        flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type:ignore [arg-type]

    return redirect(
        url_for(
            "developers.deliver.manage_form_questions",
            grant_id=grant_id,
            collection_id=collection_id,
            section_id=section_id,
            form_id=form_id,
        )
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/<uuid:collection_id>/sections/<uuid:section_id>/forms/<uuid:form_id>/questions/<uuid:question_id>/edit",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def edit_question(
    grant_id: UUID, collection_id: UUID, section_id: UUID, form_id: UUID, question_id: UUID
) -> ResponseReturnValue:
    question = get_question_by_id(question_id=question_id)
    wt_form = QuestionForm(obj=question, question_type=question.data_type)

    confirm_deletion_form = ConfirmDeletionForm()
    if "delete" in request.args:
        try:
            raise_if_question_has_any_dependencies(question)

            if confirm_deletion_form.validate_on_submit() and confirm_deletion_form.confirm_deletion.data:
                delete_question(question)
                # TODO: Flash message for deletion?
                return redirect(
                    url_for(
                        "developers.deliver.manage_form_questions",
                        grant_id=grant_id,
                        collection_id=collection_id,
                        section_id=section_id,
                        form_id=form_id,
                    )
                )
        except DependencyOrderException as e:
            flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # type:ignore [arg-type]
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                    question_id=question_id,
                )
            )

    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            update_question(
                question=question,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions(
                    last_data_source_item_is_distinct_from_others=wt_form.separate_option_if_no_items_match.data
                ),
            )
            return redirect(
                url_for(
                    "developers.deliver.manage_form_questions",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # type:ignore[attr-defined]
        except DataSourceItemReferenceDependencyException as e:
            for flash_context in e.as_flash_contexts():
                flash(flash_context, FlashMessageType.DATA_SOURCE_ITEM_DEPENDENCY_ERROR.value)  # type: ignore[arg-type]
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=collection_id,
                    section_id=section_id,
                    form_id=form_id,
                    question_id=question_id,
                )
            )

    return render_template(
        "developers/deliver/edit_question.html",
        grant=question.form.section.collection.grant,
        collection=question.form.section.collection,
        section=question.form.section,
        db_form=question.form,
        question=question,
        form=wt_form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        managed_validation_available=get_managed_validators_by_data_type(question.data_type),
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/add-condition",
    methods=["GET", "POST"],
)
@is_platform_admin
def add_question_condition_select_question(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)
    form = ConditionSelectQuestionForm(question=question)

    if form.validate_on_submit():
        depends_on_question = get_question_by_id(form.question.data)
        return redirect(
            url_for(
                "developers.deliver.add_question_condition",
                grant_id=grant_id,
                question_id=question_id,
                depends_on_question_id=depends_on_question.id,
            )
        )

    return render_template(
        "developers/deliver/add_question_condition_select_question.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/add-condition/<uuid:depends_on_question_id>",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def add_question_condition(grant_id: UUID, question_id: UUID, depends_on_question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)
    depends_on_question = get_question_by_id(depends_on_question_id)

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
    form = ConditionForm() if ConditionForm else None
    if form and form.validate_on_submit():
        expression = form.get_expression(depends_on_question)

        try:
            interfaces.collections.add_question_condition(question, interfaces.user.get_current_user(), expression)
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=question.form.section.collection.id,
                    section_id=question.form.section.id,
                    form_id=question.form.id,
                    question_id=question.id,
                )
            )
        except DuplicateValueError:
            form.form_errors.append(f"“{expression.description}” condition based on this question already exists.")

    return render_template(
        "developers/deliver/manage_question_condition_select_condition_type.html",
        question=question,
        depends_on_question=depends_on_question,
        grant=question.form.section.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/condition/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def edit_question_condition(grant_id: UUID, question_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)
    expression = question.get_expression(expression_id)
    depends_on_question = expression.managed.referenced_question

    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=question, expression=expression)
        return redirect(
            url_for(
                "developers.deliver.edit_question",
                grant_id=grant_id,
                collection_id=question.form.section.collection_id,
                section_id=question.form.section.id,
                form_id=question.form.id,
                question_id=question.id,
            )
        )

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question, expression)
    form = ConditionForm() if ConditionForm else None

    if form and form.validate_on_submit():
        updated_managed_expression = form.get_expression(depends_on_question)

        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=question.form.section.collection.id,
                    section_id=question.form.section.id,
                    form_id=question.form.id,
                    question_id=question.id,
                )
            )
        except DuplicateValueError:
            form.form_errors.append(
                f"“{updated_managed_expression.description}” condition based on this question already exists."
            )

    return render_template(
        "developers/deliver/manage_question_condition_select_condition_type.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
        depends_on_question=depends_on_question,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/add-validation",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def add_question_validation(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)

    ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
    form = ValidationForm() if ValidationForm else None
    if form and form.validate_on_submit():
        expression = form.get_expression(question)

        try:
            interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(f"“{expression.description}” validation already exists on the question.")
        else:
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=question.form.section.collection.id,
                    section_id=question.form.section.id,
                    form_id=question.form.id,
                    question_id=question.id,
                )
            )

    return render_template(
        "developers/deliver/manage_question_validation.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
    )


@developers_deliver_blueprint.route(
    "/grants/<uuid:grant_id>/collections/questions/<uuid:question_id>/validation/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@is_platform_admin
@auto_commit_after_request
def edit_question_validation(grant_id: UUID, question_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)
    expression = question.get_expression(expression_id)

    confirm_deletion_form = ConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=question, expression=expression)
        return redirect(
            url_for(
                "developers.deliver.edit_question",
                grant_id=grant_id,
                collection_id=question.form.section.collection_id,
                section_id=question.form.section.id,
                form_id=question.form.id,
                question_id=question.id,
            )
        )

    ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question, expression)
    form = ValidationForm() if ValidationForm else None

    if form and form.validate_on_submit():
        updated_managed_expression = form.get_expression(question)
        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(
                f"“{updated_managed_expression.description}” validation already exists on the question."
            )
        else:
            return redirect(
                url_for(
                    "developers.deliver.edit_question",
                    grant_id=grant_id,
                    collection_id=question.form.section.collection.id,
                    section_id=question.form.section.id,
                    form_id=question.form.id,
                    question_id=question.id,
                )
            )

    return render_template(
        "developers/deliver/manage_question_validation.html",
        question=question,
        grant=question.form.section.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
    )


@developers_deliver_blueprint.route("/submissions/<uuid:submission_id>", methods=["GET", "POST"])
@auto_commit_after_request
@is_platform_admin
def submission_tasklist(submission_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(submission_id=submission_id, source=FormRunnerState(source) if source else None)

    if runner.tasklist_form.validate_on_submit():
        if runner.complete_submission(interfaces.user.get_current_user()):
            if runner.submission.is_test:
                return redirect(
                    url_for(
                        "deliver_grant_funding.return_from_test_submission",
                        collection_id=runner.submission.collection.id,
                        finished=1,
                    )
                )

            return redirect(
                url_for(
                    "developers.deliver.manage_collection_tasks",
                    collection_id=runner.submission.collection.id,
                    grant_id=runner.submission.grant.id,
                )
            )

    return render_template(
        "developers/deliver/collection_tasklist.html",
        runner=runner,
    )


@developers_deliver_blueprint.route("/submissions/<uuid:submission_id>/<uuid:question_id>", methods=["GET", "POST"])
@is_platform_admin
@auto_commit_after_request
def ask_a_question(submission_id: UUID, question_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(
        submission_id=submission_id, question_id=question_id, source=FormRunnerState(source) if source else None
    )

    if not runner.validate_can_show_question_page():
        return redirect(runner.next_url)

    if runner.question_form and runner.question_form.validate_on_submit():
        runner.save_question_answer()
        return redirect(runner.next_url)

    return render_template("developers/deliver/ask_a_question.html", runner=runner)


@developers_deliver_blueprint.route(
    "/submissions/<uuid:submission_id>/check-yours-answers/<uuid:form_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
@is_platform_admin
def check_your_answers(submission_id: UUID, form_id: UUID) -> ResponseReturnValue:
    source = request.args.get("source")
    runner = DGFFormRunner.load(
        submission_id=submission_id, form_id=form_id, source=FormRunnerState(source) if source else None
    )

    if runner.check_your_answers_form.validate_on_submit():
        if runner.save_is_form_completed(interfaces.user.get_current_user()):
            if form_id == session.get("test_submission_form_id", None):
                return redirect(
                    url_for(
                        "deliver_grant_funding.return_from_test_submission",
                        collection_id=runner.submission.collection.id,
                        finished=1,
                    )
                )

            return redirect(runner.next_url)

    return render_template("developers/deliver/check_your_answers.html", runner=runner)


@developers_deliver_blueprint.route(
    "/collections/<uuid:collection_id>/submissions/<submission_mode:submission_mode>",
    methods=["GET"],
)
@is_platform_admin
def list_submissions_for_collection(collection_id: UUID, submission_mode: SubmissionModeEnum) -> ResponseReturnValue:
    collection = interfaces.collections.get_collection(collection_id, with_full_schema=True)

    # FIXME: optimise this to only _fetch_ the live or test submissions? The relationship will fetch all submissions
    #        at the moment and filter on the python side.
    collection = interfaces.collections.get_collection(collection_id, with_full_schema=True)
    helper = CollectionHelper(collection=collection, submission_mode=submission_mode)

    return render_template(
        "developers/deliver/list_submissions.html",
        back_link=url_for("developers.deliver.grant_developers", grant_id=collection.grant_id),
        grant=collection.grant,
        collection=collection,
        submissions=[submission for _, submission in helper.submission_helpers.items()],
        submission_mode=submission_mode,
        is_test_mode=submission_mode == SubmissionModeEnum.TEST,
    )


@developers_deliver_blueprint.route(
    "/collections/<uuid:collection_id>/submissions/<submission_mode:submission_mode>/export/<export_format>",
    methods=["GET"],
)
@is_platform_admin
def export_submissions_for_collection(
    collection_id: UUID, submission_mode: SubmissionModeEnum, export_format: str
) -> ResponseReturnValue:
    collection = interfaces.collections.get_collection(collection_id, with_full_schema=True)
    helper = CollectionHelper(collection=collection, submission_mode=submission_mode)
    if export_format.lower() == "csv":
        csv_data = helper.generate_csv_content_for_all_submissions()
        csv_buffer = io.StringIO()
        csv_buffer.write(csv_data)
        csv_buffer.seek(0)
        return send_file(
            io.BytesIO(csv_buffer.getvalue().encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{collection.name} - {submission_mode.name}.{export_format}",
            max_age=0,
        )

    else:
        abort(400)


@developers_deliver_blueprint.route("/submission/<uuid:submission_id>", methods=["GET"])
@is_platform_admin
def manage_submission(submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id=submission_id)

    return render_template(
        "developers/deliver/manage_submission.html",
        back_link=url_for(
            "developers.deliver.list_submissions_for_collection",
            collection_id=submission_helper.collection.id,
            submission_mode=submission_helper.submission.mode,
        ),
        submission_helper=submission_helper,
        grant=submission_helper.collection.grant,
        collection=submission_helper.collection,
    )
