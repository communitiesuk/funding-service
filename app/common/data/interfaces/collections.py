import uuid
from typing import TYPE_CHECKING, Any, Never, Optional, Protocol, Sequence
from uuid import UUID

from flask import current_app
from sqlalchemy import ScalarResult, and_, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.common.collections.types import AllAnswerTypes
from app.common.data.interfaces.exceptions import (
    DuplicateValueError,
    InvalidReferenceInExpression,
    flush_and_rollback_on_exceptions,
)
from app.common.data.models import (
    Collection,
    Component,
    ComponentReference,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
    Grant,
    Group,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_user import User
from app.common.data.types import (
    CollectionType,
    ExpressionType,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventKey,
    SubmissionModeEnum,
)
from app.common.expressions import ALLOWED_INTERPOLATION_REGEX, INTERPOLATE_REGEX, ExpressionContext
from app.common.expressions.managed import BaseDataSourceManagedExpression
from app.common.forms.helpers import questions_in_same_add_another_container
from app.common.qid import SafeQidMixin
from app.common.utils import slugify
from app.extensions import db
from app.types import NOT_PROVIDED, TNotProvided

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_collection(*, name: str, user: User, grant: Grant, version: int = 1, type_: CollectionType) -> Collection:
    collection = Collection(name=name, created_by=user, grant=grant, version=version, slug=slugify(name), type=type_)
    db.session.add(collection)
    return collection


def get_collection(
    collection_id: UUID,
    grant_id: UUID | None = None,
    type_: CollectionType | None = None,
    version: int | None = None,
    with_full_schema: bool = False,
) -> Collection:
    """Get a collection by ID and optionally version.

    If you do not pass a version, it will retrieve the latest version (ie highest version number).

    Note: We may wish to change this behaviour to the latest 'published' version in the future, or some other logic.
    """
    options = []
    if with_full_schema:
        options.extend(
            [
                # get all flat components to drive single batches of selectin
                # joinedload lets us avoid an exponentially increasing number of queries
                joinedload(Collection.forms).selectinload(Form._all_components).selectinload(Component.components),
                # eagerly populate the forms top level components - this is a redundant query but
                # leaves as much as possible with the ORM
                joinedload(Collection.forms).selectinload(Form.components),
            ]
        )

    filters = [Collection.id == collection_id]
    if grant_id:
        filters.append(Collection.grant_id == grant_id)
    if type_:
        filters.append(Collection.type == type_)
    if version is not None:
        filters.append(Collection.version == version)

    return (
        db.session.scalars(
            select(Collection).where(*filters).order_by(Collection.version.desc()).options(*options).limit(1)
        )
        .unique()
        .one()
    )


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_collection(collection: Collection, *, name: str) -> Collection:
    collection.name = name
    collection.slug = slugify(name)
    return collection


@flush_and_rollback_on_exceptions
def remove_add_another_answers_at_index(
    submission: Submission, add_another_container: Component, add_another_index: int
) -> Submission:
    existing_answers = submission.data.get(str(add_another_container.id), [])
    if add_another_index < 0 or add_another_index >= len(existing_answers):
        raise ValueError(
            f"Cannot remove answers at index {add_another_index} as there are "
            f"only {len(existing_answers)} existing answers"
        )

    existing_answers.pop(add_another_index)
    submission.data[str(add_another_container.id)] = existing_answers
    return submission


@flush_and_rollback_on_exceptions
def update_submission_data(
    submission: Submission, question: Question, data: AllAnswerTypes, add_another_index: int | None = None
) -> Submission:
    if not question.add_another_container:
        # this is just a single answer question
        if add_another_index is not None:
            raise ValueError("add_another_index cannot be provided for questions not within an add another container")
        submission.data[str(question.id)] = data.get_value_for_submission()
        return submission

    if add_another_index is None:
        raise ValueError("add_another_index must be provided for questions within an add another container")

    parent_container = question.add_another_container
    existing_answers = submission.data.get(str(parent_container.id), [])

    if add_another_index > len(existing_answers) or add_another_index < 0:
        raise ValueError(
            f"Cannot update answers at index {add_another_index} as there are "
            f"only {len(existing_answers)} existing answers"
        )
    if len(existing_answers) == add_another_index:
        existing_answers.append({})
    existing_answers[add_another_index][str(question.id)] = data.get_value_for_submission()

    submission.data[str(parent_container.id)] = existing_answers
    return submission


# todo: nested components
def get_all_submissions_with_mode_for_collection_with_full_schema(
    collection_id: UUID, submission_mode: SubmissionModeEnum
) -> ScalarResult[Submission]:
    """
    Use this function to get all submission data for a collection - it
    loads all the question/expression/user data at once to optimise
    performance and reduce the number of queries compared to looping
    through them all individually.
    """

    # todo: this feels redundant because this interface should probably be limited to a single collection and fetch
    #       that through a specific interface which already exists - this can then focus on submissions
    return db.session.scalars(
        select(Submission)
        .where(Submission.collection_id == collection_id)
        .where(Submission.mode == submission_mode)
        .options(
            # get all flat components to drive single batches of selectin
            # joinedload lets us avoid an exponentially increasing number of queries
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form._all_components)
            .joinedload(Component.expressions),
            # get any nested components in one go
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form._all_components)
            .selectinload(Component.components)
            .joinedload(Component.expressions),
            # eagerly populate the forms top level components - this is a redundant query but
            # leaves as much as possible with the ORM
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form.components)
            .joinedload(Component.expressions),
            selectinload(Submission.events),
            joinedload(Submission.created_by),
        )
    ).unique()


def get_submission(submission_id: UUID, with_full_schema: bool = False) -> Submission:
    options = []
    if with_full_schema:
        options.extend(
            [
                # get all flat components to drive single batches of selectin
                # joinedload lets us avoid an exponentially increasing number of queries
                joinedload(Submission.collection)
                .joinedload(Collection.forms)
                .selectinload(Form._all_components)
                .joinedload(Component.expressions),
                # get any nested components in one go
                joinedload(Submission.collection)
                .joinedload(Collection.forms)
                .selectinload(Form._all_components)
                .selectinload(Component.components)
                .joinedload(Component.expressions),
                # eagerly populate the forms top level components - this is a redundant query but
                # leaves as much as possible with the ORM
                joinedload(Submission.collection)
                .joinedload(Collection.forms)
                .selectinload(Form.components)
                .joinedload(Component.expressions),
                joinedload(Submission.events),
            ]
        )

    # We set `populate_existing` here to force a new query to be emitted to the database. The mechanics of `get_one`
    # relies on the session cache and does a lookup in the session memory based on the PK we're trying to retrieve.
    # If the object exists, no query is emitted and the options won't take effect - we would fall back to lazy loading,
    # which is n+1 select. If we don't care about fetching the full nested collection then it's fine to grab whatever is
    # cached in the session alright, but if we do specifically want all of the related objects, we want to force the
    # loading options above. This does mean that if you call this function twice with `with_full_schema=True`, it will
    # do redundant DB trips. We should try to avoid that. =]
    # If we took the principle that all relationships should be declared on the model as `lazy='raiseload'`, and we
    # specify lazy loading explicitly at all points of use, we could potentially remove the `populate_existing`
    # override below.
    return db.session.get_one(Submission, submission_id, options=options, populate_existing=bool(options))


@flush_and_rollback_on_exceptions
def create_submission(*, collection: Collection, created_by: User, mode: SubmissionModeEnum) -> Submission:
    submission = Submission(
        collection=collection,
        created_by=created_by,
        mode=mode,
        data={},
    )
    db.session.add(submission)
    return submission


def _swap_elements_in_list_and_flush(containing_list: list[Any], index_a: int, index_b: int) -> list[Any]:
    """Swaps the elements at the specified indices in the supplied list.
    If either index is outside the valid range, returns the list unchanged.

    Args:
        containing_list (list): List containing the elements to swap
        index_a (int): List index (0-based) of the first element to swap
        index_b (int): List index (0-based) of the second element to swap

    Returns:
        list: The updated list
    """
    if 0 <= index_a < len(containing_list) and 0 <= index_b < len(containing_list):
        containing_list[index_a], containing_list[index_b] = containing_list[index_b], containing_list[index_a]
    db.session.execute(text("SET CONSTRAINTS uq_form_order_collection, uq_component_order_form DEFERRED"))
    db.session.flush()
    return containing_list


def get_form_by_id(form_id: UUID, grant_id: UUID | None = None, with_all_questions: bool = False) -> Form:
    query = select(Form).where(Form.id == form_id)

    if grant_id:
        query = (
            query.join(Form.collection)
            .join(Collection.grant)
            .options(joinedload(Form.collection).joinedload(Collection.grant))
            .where(Collection.id == Form.collection_id, Collection.grant_id == grant_id)
        )

    if with_all_questions:
        # todo: this needs to be rationalised with the grant_id behaviour above, having multiple places to
        #       specify joins and options feels risky for them to collide or produce unexpected behaviour
        query = query.options(
            # get all flat components to drive single batches of selectin
            # joinedload lets us avoid an exponentially increasing number of queries
            selectinload(Form._all_components).joinedload(Component.expressions),
            # get any nested components in one go
            selectinload(Form._all_components).selectinload(Component.components).joinedload(Component.expressions),
            # eagerly populate the forms top level components - this is a redundant query but leaves as much as possible
            # with the ORM
            selectinload(Form.components).joinedload(Component.expressions),
        )

    return db.session.execute(query).scalar_one()


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_form(*, title: str, collection: Collection) -> Form:
    form = Form(
        title=title,
        collection_id=collection.id,
        collection_version=collection.version,
        slug=slugify(title),
    )
    collection.forms.append(form)
    db.session.add(form)
    return form


@flush_and_rollback_on_exceptions
def move_form_up(form: Form) -> Form:
    _swap_elements_in_list_and_flush(form.collection.forms, form.order, form.order - 1)
    return form


@flush_and_rollback_on_exceptions
def move_form_down(form: Form) -> Form:
    _swap_elements_in_list_and_flush(form.collection.forms, form.order, form.order + 1)
    return form


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_form(form: Form, *, title: str) -> Form:
    form.title = title
    form.slug = slugify(title)
    return form


@flush_and_rollback_on_exceptions
def _create_data_source(question: Question, items: list[str]) -> None:
    data_source = DataSource(id=uuid.uuid4(), question_id=question.id)
    db.session.add(data_source)

    if len(set(slugify(item) for item in items)) != len(items):
        # If this error occurs, it's probably because QuestionForm does not check for duplication between the
        # main options and the 'Other' option. Might need to add that if this has triggered; but avoiding
        # now because I consider it unlikely. This will protect us even if it's not the best UX.
        raise ValueError("No duplicate data source items are allowed")

    data_source_items = []
    for choice in items:
        data_source_items.append(DataSourceItem(data_source_id=data_source.id, key=slugify(choice), label=choice))
    data_source.items = data_source_items


@flush_and_rollback_on_exceptions
def _update_data_source(question: Question, items: list[str]) -> None:
    existing_choices_map = {choice.key: choice for choice in question.data_source.items}
    for item in items:
        if slugify(item) in existing_choices_map:
            existing_choices_map[slugify(item)].label = item

    if len(set(slugify(item) for item in items)) != len(items):
        # If this error occurs, it's probably because QuestionForm does not check for duplication between the
        # main options and the 'Other' option. Might need to add that if this has triggered; but avoiding
        # now because I consider it unlikely. This will protect us even if it's not the best UX.
        raise ValueError("No duplicate data source items are allowed")

    new_choices = [
        existing_choices_map.get(
            slugify(choice),
            DataSourceItem(data_source_id=question.data_source.id, key=slugify(choice), label=choice),
        )
        for choice in items
    ]

    db.session.execute(text("SET CONSTRAINTS uq_data_source_id_order DEFERRED"))

    to_delete = [item for item in question.data_source.items if item not in new_choices]
    raise_if_data_source_item_reference_dependency(question, to_delete)
    for item_to_delete in to_delete:
        db.session.delete(item_to_delete)
    question.data_source.items = new_choices
    question.data_source.items.reorder()  # type: ignore[attr-defined]


@flush_and_rollback_on_exceptions
def create_question(
    form: Form,
    *,
    text: str,
    hint: str,
    name: str,
    data_type: QuestionDataType,
    expression_context: ExpressionContext,
    parent: Optional[Group] = None,
    items: list[str] | None = None,
    presentation_options: QuestionPresentationOptions | None = None,
) -> Question:
    question = Question(
        text=text,
        form_id=form.id,
        slug=slugify(text),
        hint=hint,
        name=name,
        data_type=data_type,
        presentation_options=presentation_options,
        parent_id=parent.id if parent else None,
    )
    owner = parent or form
    owner.components.append(question)
    db.session.add(question)

    try:
        _validate_and_sync_component_references(question, expression_context)
        db.session.flush()
    except IntegrityError as e:
        # todo: check devs view on this, this is because other constraints (like the check constraint introduced here)
        #       are not because of duplicated values - the convention based method doesn't feel ideal but this setup
        #       is already working on a few assumptions of things lining up in different places. This just raises
        #       the ORM error if we're not guessing its a duplicate value error based on it being a unique constraint
        if e.orig.diag and e.orig.diag.constraint_name and e.orig.diag.constraint_name.startswith("uq_"):  # type: ignore[union-attr]
            raise DuplicateValueError(e) from e
        raise e

    if items is not None:
        _create_data_source(question, items)

    return question


def raise_if_group_cannot_be_add_another(group: Group) -> None:
    if group.contains_add_another_components:
        raise GroupContainsAddAnotherException(
            group=group,
            message="You cannot set a group to be add another if it already contains add another components",
        )
    if group.contains_questions_depended_on_elsewhere:
        raise AddAnotherDependencyException(
            message="You cannot set a group to be add another if questions in the group are depended on "
            "by other components",
            component=group,
            referenced_question=next(
                component for component in group.cached_all_components if len(component.depended_on_by) > 0
            ),
        )
    if group.parent and group.parent.add_another_container:
        raise AddAnotherNotValidException(
            "You cannot set a group to be add another if it is nested inside an add another group",
            component=group,
            add_another_container=group.parent.add_another_container,
        )


def raise_if_nested_group_creation_not_valid_here(parent: Group | None = None) -> None:
    if parent:
        if not parent.can_have_child_group:
            raise NestedGroupException(
                "You cannot create a nested group at this level",
                parent_group=parent,
                nesting_level=parent.nested_group_levels + 1,
            )
        if parent.same_page:
            raise NestedGroupDisplayTypeSamePageException(
                "You cannot create a nested group if the parent is set to display all questions on the same page",
                parent_group=parent,
            )


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_group(
    form: Form,
    *,
    text: str,
    name: Optional[str] = None,
    parent: Optional[Group] = None,
    presentation_options: QuestionPresentationOptions | None = None,
) -> Group:
    # If this group is nested, ensure it meets rules for nesting groups
    # This is a safety check as we don't allow users to create nested groups when these rules aren't met
    raise_if_nested_group_creation_not_valid_here(parent=parent)
    group = Group(
        text=text,
        name=name or text,
        slug=slugify(text),
        form_id=form.id,
        parent_id=parent.id if parent else None,
        presentation_options=presentation_options,
    )
    owner = parent or form
    owner.components.append(group)
    db.session.add(group)
    return group


# todo: rename
def get_question_by_id(question_id: UUID) -> Question:
    return db.session.get_one(
        Question,
        question_id,
        options=[
            joinedload(Question.form).joinedload(Form.collection).joinedload(Collection.grant),
        ],
    )


def get_group_by_id(group_id: UUID) -> Group:
    return db.session.get_one(
        Group,
        group_id,
        options=[
            joinedload(Group.form).joinedload(Form.collection).joinedload(Collection.grant),
        ],
    )


def get_expression_by_id(expression_id: UUID) -> Expression:
    return db.session.get_one(
        Expression,
        expression_id,
        options=[
            joinedload(Expression.question)
            .joinedload(Component.form)
            .joinedload(Form.collection)
            .joinedload(Collection.grant)
        ],
    )


def get_component_by_id(component_id: UUID) -> Component:
    return db.session.get_one(Component, component_id)


class FlashableException(Protocol):
    def as_flash_context(self) -> dict[str, str | bool]: ...


class DependencyOrderException(Exception, FlashableException):
    def __init__(self, message: str, component: Component, depends_on_component: Component):
        super().__init__(message)
        self.message = message
        self.question = component
        self.depends_on_question = depends_on_component

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.question.form.collection.grant_id),  # Required for URL routing
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            "question_is_group": self.question.is_group,
            # currently you can't depend on the outcome to a generic component (like a group)
            # so question continues to make sense here - we should review that naming if that
            # functionality changes
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
            "depends_on_question_is_group": self.depends_on_question.is_group,
        }


class IncompatibleDataTypeException(Exception):
    def __init__(self, message: str, component: Component, depends_on_component: Component):
        super().__init__(message)
        self.message = message
        self.question = component
        self.depends_on_question = depends_on_component

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.question.form.collection.grant_id),  # Required for URL routing
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
        }


class DataSourceItemReferenceDependencyException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        question_being_edited: Question,
        data_source_item_dependency_map: dict[Component, set[DataSourceItem]],
    ):
        super().__init__(message)
        self.message = message
        self.question_being_edited = question_being_edited
        self.data_source_item_dependency_map = data_source_item_dependency_map

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        for dependent_question, data_source_items in self.data_source_item_dependency_map.items():
            flash_context: dict[str, str | bool] = {
                "message": self.message,
                "question_id": str(dependent_question.id),
                "question_text": dependent_question.text,
                "question_is_group": dependent_question.is_group,
                "depends_on_question_id": str(self.question_being_edited.id),
                "depends_on_question_text": self.question_being_edited.text,
                "depends_on_question_is_group": self.question_being_edited.is_group,
                "depends_on_items_text": ", ".join(data_source_item.label for data_source_item in data_source_items),
            }
            flash_contexts.append(flash_context)
        return flash_contexts


class NestedGroupException(Exception, FlashableException):
    def __init__(self, message: str, parent_group: Group, nesting_level: int):
        super().__init__(message)
        self.message = message
        self.parent_group = parent_group
        self.nesting_level = nesting_level

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        flash_context: dict[str, str | bool] = {
            "message": self.message,
            "parent_group_name": self.parent_group.name,
            "parent_group_id": str(self.parent_group.id),
            "nesting_level": str(self.nesting_level),
            "max_nesting_level": str(current_app.config["MAX_NESTED_GROUP_LEVELS"]),
            "grant_id": str(self.parent_group.form.collection.grant_id),
        }
        flash_contexts.append(flash_context)
        return flash_contexts


class GroupContainsAddAnotherException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        group: Group,
    ):
        super().__init__(message)
        self.message = message
        self.group = group

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        flash_context: dict[str, str | bool] = {
            "message": self.message,
            "group_name": self.group.name,
            "group_id": str(self.group.id),
            "grant_id": str(self.group.form.collection.grant_id),
        }
        flash_contexts.append(flash_context)
        return flash_contexts


class NestedGroupDisplayTypeSamePageException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        parent_group: Group,
    ):
        super().__init__(message)
        self.message = message
        self.parent_group = parent_group

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        flash_context: dict[str, str | bool] = {
            "message": self.message,
            "parent_group_name": self.parent_group.name,
            "parent_group_id": str(self.parent_group.id),
            "grant_id": str(self.parent_group.form.collection.grant_id),
        }
        flash_contexts.append(flash_context)
        return flash_contexts


# todo: we might want something more generalisable that checks all order dependencies across a form
#       but this gives us the specific result we want for the UX for now
def _check_component_order_dependency(component: Component, swap_component: Component) -> None:
    # fetching the entire schema means whatever is calling this doesn't have to worry about
    # guaranteeing lazy loading performance behaviour
    _ = get_form_by_id(component.form_id, with_all_questions=True)

    # we could be comparing to either an individual question or a group of multiple questions so collect those
    # as lists to compare against each other
    child_components = [component] + (
        [c for c in component.cached_all_components] if isinstance(component, Group) else []
    )
    child_swap_components = [swap_component] + (
        [c for c in swap_component.cached_all_components] if isinstance(swap_component, Group) else []
    )

    for c in child_components:
        component_name = "question_groups" if c.is_group else "questions"
        for cr in c.owned_component_references:
            if cr.depends_on_component in child_swap_components:
                raise DependencyOrderException(
                    f"You cannot move {component_name} above answers they depend on",
                    component,
                    swap_component,
                )

    for c in child_swap_components:
        component_name = "question_groups" if c.is_group else "questions"
        for cr in c.owned_component_references:
            if cr.depends_on_component in child_components:
                raise DependencyOrderException(
                    f"You cannot move answers below {component_name} that depend on them",
                    swap_component,
                    component,
                )


# todo: persisting global order (depth + order) of components would help short circuit a lot of these checks
def is_component_dependency_order_valid(component: Component, depends_on_component: Component) -> bool:
    # fetching the entire schema means whatever is calling this doesn't have to worry about
    # guaranteeing lazy loading performance behaviour
    form = get_form_by_id(component.form_id, with_all_questions=True)
    return form.cached_all_components.index(component) > form.cached_all_components.index(depends_on_component)


def raise_if_question_has_any_dependencies(question: Question | Group) -> Never | None:
    child_components_ids = [
        c.id for c in [question] + (question.cached_all_components if isinstance(question, Group) else [])
    ]
    component_reference = (
        db.session.query(ComponentReference)
        .where(ComponentReference.depends_on_component_id.in_(child_components_ids))
        .all()
    )
    if component_reference:
        raise DependencyOrderException(
            "You cannot delete an answer that other questions depend on",
            component_reference[0].component,
            question,  # TODO: this could be component_reference[0].depends_on_component?
        )

    return None


def raise_if_group_questions_depend_on_each_other(group: Group) -> Never | None:
    child_components_ids = [c.id for c in group.cached_questions]
    component_reference = (
        db.session.query(ComponentReference)
        .where(
            and_(
                ComponentReference.component_id.in_(child_components_ids),
                ComponentReference.depends_on_component_id.in_(child_components_ids),
            )
        )
        .all()
    )
    if component_reference:
        raise DependencyOrderException(
            "You cannot set a group to be same page if it contains questions that depend on each other",
            component_reference[0].component,
            component_reference[0].depends_on_component,
        )

    return None


def raise_if_data_source_item_reference_dependency(
    question: Question, items_to_delete: Sequence[DataSourceItem]
) -> Never | None:
    data_source_item_dependency_map: dict[Component, set[DataSourceItem]] = {}
    for data_source_item in items_to_delete:
        for reference in data_source_item.component_references:
            dependent_component = reference.component
            if dependent_component not in data_source_item_dependency_map:
                data_source_item_dependency_map[dependent_component] = set()
            data_source_item_dependency_map[dependent_component].add(data_source_item)

    if data_source_item_dependency_map:
        db.session.rollback()
        raise DataSourceItemReferenceDependencyException(
            "You cannot delete or change an option that other questions depend on.",
            question_being_edited=question,
            data_source_item_dependency_map=data_source_item_dependency_map,
        )
    return None


class AddAnotherDependencyException(Exception, FlashableException):
    def __init__(self, message: str, component: Component, referenced_question: Component):
        super().__init__(message)
        self.message = message
        self.component = component
        self.referenced_question = referenced_question

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.component.form.collection.grant_id),  # Required for URL routing
            "component_id": str(self.component.id),
            "component_text": self.component.text,
            "referenced_question_id": str(self.referenced_question.id),
            "referenced_question_text": self.referenced_question.text,
        }


class AddAnotherNotValidException(Exception, FlashableException):
    def __init__(self, message: str, component: Component, add_another_container: Component):
        super().__init__(message)
        self.message = message
        self.component = component
        self.add_another_container = add_another_container

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.component.form.collection.grant_id),  # Required for URL routing
            "component_id": str(self.component.id),
            "component_text": self.component.text,
            "add_another_container_id": str(self.add_another_container.id),
            "add_another_container_text": self.add_another_container.text,
        }


def raise_if_add_another_not_valid_here(component: Component) -> None:
    if not component.add_another:
        return
    if component.parent and component.parent.add_another_container:
        raise AddAnotherNotValidException(
            "You cannot create an add another component within an add another group",
            component,
            component.parent.add_another_container,
        )


@flush_and_rollback_on_exceptions
def move_component_up(component: Component) -> Component:
    swap_component = component.container.components[component.order - 1]
    _check_component_order_dependency(component, swap_component)
    _swap_elements_in_list_and_flush(component.container.components, component.order, swap_component.order)
    return component


@flush_and_rollback_on_exceptions
def move_component_down(component: Component) -> Component:
    swap_component = component.container.components[component.order + 1]
    _check_component_order_dependency(component, swap_component)
    _swap_elements_in_list_and_flush(component.container.components, component.order, swap_component.order)
    return component


def group_name_exists(name: str, form_id: UUID) -> bool:
    statement = select(Group).where(Group.name == name, Group.form_id == form_id)
    group = db.session.scalar(statement)
    return group is not None


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_group(
    group: Group,
    expression_context: ExpressionContext,
    *,
    name: str | TNotProvided = NOT_PROVIDED,
    presentation_options: QuestionPresentationOptions | TNotProvided = NOT_PROVIDED,
    guidance_heading: str | None | TNotProvided = NOT_PROVIDED,
    guidance_body: str | None | TNotProvided = NOT_PROVIDED,
    add_another: bool | TNotProvided = NOT_PROVIDED,
    add_another_guidance_body: str | None | TNotProvided = NOT_PROVIDED,
) -> Group:
    if name is not NOT_PROVIDED:
        group.name = name  # ty: ignore[invalid-assignment]
        group.text = name  # ty: ignore[invalid-assignment]
        group.slug = slugify(name)  # ty: ignore[invalid-argument-type]

    if presentation_options is not NOT_PROVIDED:
        if (
            group.presentation_options.show_questions_on_the_same_page is not True
            and presentation_options.show_questions_on_the_same_page is True
        ):
            if group.has_nested_groups:
                raise NestedGroupDisplayTypeSamePageException(
                    "You cannot set a group to display all questions on the same page if it has nested groups",
                    parent_group=group,
                )
            try:
                raise_if_group_questions_depend_on_each_other(group)
            except DependencyOrderException as e:
                db.session.rollback()
                raise e

        # presentation options for groups can be spread out across multiple forms/ setting pages
        # override the provided fields without removing the existing settings for now, we might
        # want to switch to mutating the existing object in the future instead
        group.presentation_options = group.presentation_options.model_copy(
            update=presentation_options.model_dump(exclude_unset=True)
        )

    if guidance_heading is not NOT_PROVIDED:
        group.guidance_heading = guidance_heading  # ty: ignore[invalid-assignment]

    if guidance_body is not NOT_PROVIDED:
        group.guidance_body = guidance_body  # ty: ignore[invalid-assignment]

    if add_another is not NOT_PROVIDED:
        if group.add_another is not True and add_another is True:
            raise_if_group_cannot_be_add_another(group)

        group.add_another = add_another

    if add_another_guidance_body is not NOT_PROVIDED:
        group.add_another_guidance_body = add_another_guidance_body  # ty: ignore[invalid-assignment]

    _validate_and_sync_component_references(group, expression_context)

    # This is extreme and reasonably un-optimised, but it does provide a high level of assurance against being able to
    # break references within any child components. We should aim to have suitable checks higher up to provide a better
    # user experience/error handling though.
    for child in group.cached_all_components:
        _validate_and_sync_component_references(child, expression_context)

    return group


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_question(
    question: Question,
    expression_context: ExpressionContext,
    *,
    text: str | TNotProvided = NOT_PROVIDED,
    name: str | TNotProvided = NOT_PROVIDED,
    hint: str | None | TNotProvided = NOT_PROVIDED,
    items: list[str] | None | TNotProvided = NOT_PROVIDED,
    presentation_options: QuestionPresentationOptions | TNotProvided = NOT_PROVIDED,
    guidance_heading: str | None | TNotProvided = NOT_PROVIDED,
    guidance_body: str | None | TNotProvided = NOT_PROVIDED,
) -> Question:
    if text is not NOT_PROVIDED and text is not None:
        question.text = text  # ty: ignore[invalid-assignment]
        question.slug = slugify(text)  # ty: ignore[invalid-argument-type]

    if hint is not NOT_PROVIDED:
        question.hint = hint  # ty: ignore[invalid-assignment]

    if name is not NOT_PROVIDED:
        question.name = name  # ty: ignore[invalid-assignment]

    if presentation_options is not NOT_PROVIDED:
        question.presentation_options = presentation_options or QuestionPresentationOptions()  # ty: ignore[invalid-assignment]

    if guidance_heading is not NOT_PROVIDED:
        question.guidance_heading = guidance_heading  # ty: ignore[invalid-assignment]

    if guidance_body is not NOT_PROVIDED:
        question.guidance_body = guidance_body  # ty: ignore[invalid-assignment]

    if items is not NOT_PROVIDED and items is not None:
        _update_data_source(question, items)  # ty: ignore[invalid-argument-type]

    _validate_and_sync_component_references(question, expression_context)
    return question


@flush_and_rollback_on_exceptions
def add_submission_event(
    submission: Submission, key: SubmissionEventKey, user: User, form: Form | None = None
) -> Submission:
    submission.events.append(SubmissionEvent(key=key, created_by=user, form=form))
    return submission


@flush_and_rollback_on_exceptions
def clear_submission_events(submission: Submission, key: SubmissionEventKey, form: Form | None = None) -> Submission:
    submission.events = [x for x in submission.events if not (x.key == key and (x.form == form if form else True))]
    return submission


def get_referenced_data_source_items_by_managed_expression(
    managed_expression: "BaseDataSourceManagedExpression",
) -> Sequence[DataSourceItem]:
    referenced_data_source_items = db.session.scalars(
        select(DataSourceItem).where(
            DataSourceItem.data_source == managed_expression.referenced_question.data_source,
            DataSourceItem.key.in_([item["key"] for item in managed_expression.referenced_data_source_items]),
        )
    ).all()
    return referenced_data_source_items


def _validate_and_sync_expression_references(expression: Expression) -> None:
    if not expression.is_managed:
        raise NotImplementedError("Cannot handle un-managed expressions yet")

    # TODO: When an expression can target multiple questions, this will need refactoring to support that.
    references: list[ComponentReference] = []

    if not expression.is_managed:
        raise ValueError("Cannot handle un-managed expressions yet")

    managed = expression.managed
    if isinstance(managed, BaseDataSourceManagedExpression):
        referenced_data_source_items = get_referenced_data_source_items_by_managed_expression(
            managed_expression=managed
        )

        # TODO: Support data sources that are independent of components(questions), eg when ee have platform-level
        #       data sources.
        for referenced_data_source_item in referenced_data_source_items:
            cr = ComponentReference(
                component=expression.question,
                expression=expression,
                depends_on_component=referenced_data_source_item.data_source.question,
                depends_on_data_source_item=referenced_data_source_item,
            )
            db.session.add(cr)
            references.append(cr)
    else:
        cr = ComponentReference(
            depends_on_component=expression.managed.referenced_question,
            component=expression.question,
            expression=expression,
        )
        db.session.add(cr)
        references.append(cr)

    for referenced_question_id in managed.expression_referenced_question_ids:
        referenced_question = get_question_by_id(referenced_question_id)

        if not is_component_dependency_order_valid(managed.referenced_question, referenced_question):
            raise DependencyOrderException(
                "Cannot add a managed expression that references a later question",
                managed.referenced_question,
                referenced_question,
            )

        if referenced_question.data_type != managed.referenced_question.data_type:
            raise IncompatibleDataTypeException(
                "Expression cannot reference question of incompatible data type",
                managed.referenced_question,
                referenced_question,
            )

        if referenced_question.add_another_container and not questions_in_same_add_another_container(
            managed.referenced_question, referenced_question
        ):
            raise AddAnotherDependencyException(
                "Cannot add managed condition that depends on an add another question",
                managed.referenced_question,
                referenced_question,
            )

        cr = ComponentReference(
            component=expression.question,
            expression=expression,
            depends_on_component=referenced_question,
        )
        db.session.add(cr)
        references.append(cr)

    expression.component_references = references


def _validate_and_sync_component_references(component: Component, expression_context: ExpressionContext) -> None:  # noqa: C901
    """Scan the given component for references to another component in its text, hint, and guidance.

    Enforce our current feature scope constraint: any expression for interpolation currently must be a 'simple'
    statement. By that we mean: use a single value and do nothing else to it.

    This is a product constraint rather than a strict technical constraint right now as it simplifies
    implementation and removes a number of edge cases/concerns. We may remove this scope limiter in the future
    but recognise that doing so will need further product+design+technical thinking, which we're avoiding
    for now.
    """
    # Remove any references that are coming *from* `component`; we'll regenerate them all below
    db.session.execute(delete(ComponentReference).where(ComponentReference.component == component))

    for expression in component.expressions:
        _validate_and_sync_expression_references(expression)

    references_to_set_up: set[tuple[UUID, UUID]] = set()
    field_names = ["text", "hint", "guidance_body"]
    for field_name in field_names:
        value = getattr(component, field_name)
        if value is None:
            continue

        for match in INTERPOLATE_REGEX.finditer(value):
            wrapped_ref, inner_ref = match.group(0), match.group(1).strip()

            if ALLOWED_INTERPOLATION_REGEX.search(inner_ref) is not None:
                raise InvalidReferenceInExpression(
                    f"Reference is not valid: {wrapped_ref}",
                    field_name=field_name,
                    bad_reference=wrapped_ref,
                )

            # TODO: When we allow complex references (eg not just a single reference but some combination of references
            #       such as `q_id1 + q_id2`) then this logic will need to handle that.
            if not expression_context.is_valid_reference(inner_ref):
                raise InvalidReferenceInExpression(
                    f"Reference is not valid: {wrapped_ref}",
                    field_name=field_name,
                    bad_reference=wrapped_ref,
                )

            # If `is_valid_referencee` above is True, then we know that we have a QID that points to a question in the
            # same collection - but not necessarily the same form.
            if question_id := SafeQidMixin.safe_qid_to_id(inner_ref):
                question = db.session.get_one(Question, question_id)
                if question.form_id != component.form_id:
                    raise InvalidReferenceInExpression(
                        f"Reference is not valid: {wrapped_ref}", field_name=field_name, bad_reference=wrapped_ref
                    )

                # Prevent manually injecting a reference to a question that appears later in the same form
                if question.form.global_component_index(question) >= question.form.global_component_index(component):
                    raise InvalidReferenceInExpression(
                        f"Reference is not valid: {wrapped_ref}", field_name=field_name, bad_reference=wrapped_ref
                    )

                if (
                    question.parent
                    and component.parent
                    and question.parent.is_group
                    and component.parent.is_group
                    and question.parent.id == component.parent.id
                ):
                    if question.parent.same_page:
                        raise InvalidReferenceInExpression(
                            f"Reference is not valid: {wrapped_ref}", field_name=field_name, bad_reference=wrapped_ref
                        )

                references_to_set_up.add((component.id, question.id))

    for component_id, depends_on_component_id in references_to_set_up:
        db.session.add(ComponentReference(component_id=component_id, depends_on_component_id=depends_on_component_id))


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def add_component_condition(component: Component, user: User, managed_expression: "ManagedExpression") -> Component:
    if not is_component_dependency_order_valid(component, managed_expression.referenced_question):
        raise DependencyOrderException(
            "Cannot add managed condition that depends on a later question",
            component,
            managed_expression.referenced_question,
        )

    if managed_expression.referenced_question.add_another_container and not questions_in_same_add_another_container(
        component, managed_expression.referenced_question
    ):
        raise AddAnotherDependencyException(
            "Cannot add managed condition that depends on an add another question",
            component,
            managed_expression.referenced_question,
        )

    expression = Expression.from_managed(managed_expression, user)
    component.expressions.append(expression)

    _validate_and_sync_expression_references(expression)

    if component.parent and component.parent.same_page:
        raise_if_group_questions_depend_on_each_other(component.parent)

    return component


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def add_question_validation(question: Question, user: User, managed_expression: "ManagedExpression") -> Question:
    expression = Expression(
        statement=managed_expression.statement,
        context=managed_expression.model_dump(mode="json"),
        created_by=user,
        type_=ExpressionType.VALIDATION,
        managed_name=managed_expression._key,
    )
    question.expressions.append(expression)
    _validate_and_sync_expression_references(expression)
    return question


def get_expression(expression_id: UUID) -> Expression:
    return db.session.get_one(Expression, expression_id)


@flush_and_rollback_on_exceptions
def remove_question_expression(question: Component, expression: Expression) -> Component:
    question.expressions.remove(expression)
    return question


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_question_expression(expression: Expression, managed_expression: "ManagedExpression") -> Expression:
    expression.statement = managed_expression.statement
    expression.context = managed_expression.model_dump(mode="json")
    expression.managed_name = managed_expression._key

    _validate_and_sync_expression_references(expression)
    return expression


@flush_and_rollback_on_exceptions
def delete_collection(collection: Collection) -> None:
    if collection.live_submissions:
        db.session.rollback()
        raise ValueError("Cannot delete collection with live submissions")

    db.session.delete(collection)


@flush_and_rollback_on_exceptions
def delete_form(form: Form) -> None:
    db.session.delete(form)
    form.collection.forms = [f for f in form.collection.forms if f.id != form.id]  # type: ignore[assignment]
    form.collection.forms.reorder()  # Force all other forms to update their `order` attribute
    db.session.execute(text("SET CONSTRAINTS uq_form_order_collection DEFERRED"))


@flush_and_rollback_on_exceptions
def delete_question(question: Question | Group) -> None:
    raise_if_question_has_any_dependencies(question)
    db.session.delete(question)
    if question in question.container.components:
        question.container.components.remove(question)
    question.container.components.reorder()
    db.session.execute(text("SET CONSTRAINTS uq_component_order_form DEFERRED"))


@flush_and_rollback_on_exceptions
def delete_collection_test_submissions_created_by_user(collection: Collection, created_by_user: User) -> None:
    # We're trying to rely less on ORM relationships and cascades in delete queries so here we explicitly delete all
    # SubmissionEvents related to the `created_by_user`'s test submissions for that collection version, and then
    # subsequently delete the submissions.

    submission_ids = db.session.scalars(
        select(Submission.id).where(
            Submission.collection_id == collection.id,
            Submission.collection_version == collection.version,
            Submission.created_by_id == created_by_user.id,
            Submission.mode == SubmissionModeEnum.TEST,
        )
    ).all()

    db.session.execute(delete(SubmissionEvent).where(SubmissionEvent.submission_id.in_(submission_ids)))

    db.session.execute(
        delete(Submission).where(
            Submission.id.in_(submission_ids),
        )
    )
