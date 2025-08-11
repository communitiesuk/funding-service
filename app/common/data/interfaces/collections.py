import uuid
from typing import TYPE_CHECKING, Any, Never, Optional, Protocol, Sequence
from uuid import UUID

from sqlalchemy import ScalarResult, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.common.collections.types import AllAnswerTypes
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import (
    Collection,
    Component,
    DataSource,
    DataSourceItem,
    DataSourceItemReference,
    Expression,
    Form,
    Grant,
    Group,
    Question,
    Section,
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
from app.common.expressions.managed import BaseDataSourceManagedExpression
from app.common.utils import slugify
from app.constants import DEFAULT_SECTION_NAME
from app.extensions import db
from app.types import NOT_PROVIDED, TNotProvided

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


def create_collection(*, name: str, user: User, grant: Grant, version: int = 1, type_: CollectionType) -> Collection:
    collection = Collection(name=name, created_by=user, grant=grant, version=version, slug=slugify(name), type=type_)
    db.session.add(collection)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e

    # All collections must have at least 1 section; we provide a default to get started with.
    create_section(title=DEFAULT_SECTION_NAME, collection=collection)

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
                joinedload(Collection.sections).joinedload(Section.forms).selectinload(Form._all_components),
                # get any nested components in one go
                joinedload(Collection.sections)
                .joinedload(Section.forms)
                .selectinload(Form._all_components)
                # .selectinload(Component.components.and_(Component.type == ComponentType.GROUP)),
                .selectinload(Component.components),
                # eagerly populate the forms top level components - this is a redundant query but
                # leaves as much as possible with the ORM
                joinedload(Collection.sections).joinedload(Section.forms).selectinload(Form.components),
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


def update_collection(collection: Collection, *, name: str) -> Collection:
    collection.name = name
    collection.slug = slugify(name)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return collection


def update_submission_data(submission: Submission, question: Question, data: AllAnswerTypes) -> Submission:
    submission.data[str(question.id)] = data.get_value_for_submission()
    db.session.flush()
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
            .joinedload(Collection.sections)
            .joinedload(Section.forms)
            .selectinload(Form._all_components)
            .joinedload(Component.expressions),
            # get any nested components in one go
            joinedload(Submission.collection)
            .joinedload(Collection.sections)
            .joinedload(Section.forms)
            .selectinload(Form._all_components)
            .selectinload(Component.components)
            .joinedload(Component.expressions),
            # eagerly populate the forms top level components - this is a redundant query but
            # leaves as much as possible with the ORM
            joinedload(Submission.collection)
            .joinedload(Collection.sections)
            .joinedload(Section.forms)
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
                .joinedload(Collection.sections)
                .joinedload(Section.forms)
                .selectinload(Form._all_components),
                # get any nested components in one go
                joinedload(Submission.collection)
                .joinedload(Collection.sections)
                .joinedload(Section.forms)
                .selectinload(Form._all_components)
                .selectinload(Component.components),
                # eagerly populate the forms top level components - this is a redundant query but
                # leaves as much as possible with the ORM
                joinedload(Submission.collection)
                .joinedload(Collection.sections)
                .joinedload(Section.forms)
                .selectinload(Form.components),
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


def create_submission(*, collection: Collection, created_by: User, mode: SubmissionModeEnum) -> Submission:
    submission = Submission(
        collection=collection,
        created_by=created_by,
        mode=mode,
        data={},
    )
    db.session.add(submission)
    db.session.flush()
    return submission


def create_section(*, title: str, collection: Collection) -> Section:
    section = Section(title=title, collection_id=collection.id, slug=slugify(title))
    collection.sections.append(section)
    db.session.add(section)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section


def get_section_by_id(section_id: UUID) -> Section:
    return db.session.get_one(Section, section_id)


def update_section(section: Section, *, title: str) -> Section:
    section.title = title
    section.slug = slugify(title)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section


def swap_elements_in_list_and_flush(containing_list: list[Any], index_a: int, index_b: int) -> list[Any]:
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
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_component_order_form DEFERRED")
    )
    db.session.flush()
    return containing_list


def move_section_up(section: Section) -> Section:
    """Move a section up in the order, which means move it lower in the list."""
    swap_elements_in_list_and_flush(section.collection.sections, section.order, section.order - 1)

    return section


def move_section_down(section: Section) -> Section:
    """Move a section down in the order, which means move it higher in the list."""
    swap_elements_in_list_and_flush(section.collection.sections, section.order, section.order + 1)
    return section


def get_form_by_id(form_id: UUID, grant_id: UUID | None = None, with_all_questions: bool = False) -> Form:
    query = select(Form).where(Form.id == form_id)

    if grant_id:
        query = (
            query.join(Form.section)
            .join(Section.collection)
            .join(Collection.grant)
            .options(joinedload(Form.section).joinedload(Section.collection).joinedload(Collection.grant))
            .where(Collection.grant_id == grant_id)
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


def create_form(*, title: str, section: Section) -> Form:
    form = Form(title=title, section_id=section.id, slug=slugify(title))
    section.forms.append(form)
    db.session.add(form)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


def move_form_up(form: Form) -> Form:
    swap_elements_in_list_and_flush(form.section.forms, form.order, form.order - 1)
    return form


def move_form_down(form: Form) -> Form:
    swap_elements_in_list_and_flush(form.section.forms, form.order, form.order + 1)
    return form


def update_form(form: Form, *, title: str, section_id: uuid.UUID | TNotProvided = NOT_PROVIDED) -> Form:
    form.title = title
    form.slug = slugify(title)

    if section_id is not NOT_PROVIDED:
        db.session.execute(text("SET CONSTRAINTS uq_form_order_section DEFERRED"))
        new_section = get_section_by_id(section_id)  # ty: ignore[invalid-argument-type]
        original_section = form.section
        form.section = new_section

        new_section.forms.reorder()
        original_section.forms.reorder()

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


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

    db.session.flush()


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

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise e


def _update_data_source_references(
    expression: "Expression", managed_expression: "BaseDataSourceManagedExpression"
) -> Expression:
    referenced_data_source_items = get_referenced_data_source_items_by_managed_expression(
        managed_expression=managed_expression
    )
    for dsir in expression.data_source_item_references:
        db.session.delete(dsir)
    expression.data_source_item_references = [
        DataSourceItemReference(expression_id=expression.id, data_source_item_id=referenced_data_source_item.id)
        for referenced_data_source_item in referenced_data_source_items
    ]
    return expression


def create_question(
    form: Form,
    *,
    text: str,
    hint: str,
    name: str,
    data_type: QuestionDataType,
    parent: Optional[Component] = None,
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
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()

        # todo: check devs view on this, this is because other constraints (like the check constraint introduced here)
        #       are not because of duplicated values - the convention based method doesn't feel ideal but this setup
        #       is already working on a few assumptions of things lining up in different places. This just raises
        #       the ORM error if we're not guessing its a duplicate value error based on it being a unique constraint
        if e.orig.diag and e.orig.diag.constraint_name and e.orig.diag.constraint_name.startswith("uq_"):  # type: ignore[union-attr]
            raise DuplicateValueError(e) from e
        raise e

    if items is not None:
        _create_data_source(question, items)
        db.session.flush()

    return question


def create_group(form: Form, *, text: str, name: Optional[str] = None, parent: Optional[Group] = None) -> Group:
    group = Group(
        text=text, name=name or text, slug=slugify(text), form_id=form.id, parent_id=parent.id if parent else None
    )
    owner = parent or form
    owner.components.append(group)
    db.session.add(group)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e

    return group


# todo: rename
def get_question_by_id(question_id: UUID) -> Question:
    return db.session.get_one(
        Question,
        question_id,
        options=[
            joinedload(Question.form)
            .joinedload(Form.section)
            .joinedload(Section.collection)
            .joinedload(Collection.grant),
        ],
    )


def get_expression_by_id(expression_id: UUID) -> Expression:
    return db.session.get_one(
        Expression,
        expression_id,
        options=[
            joinedload(Expression.question)
            .joinedload(Question.form)
            .joinedload(Form.section)
            .joinedload(Section.collection)
            .joinedload(Collection.grant)
        ],
    )


def get_component_by_id(component_id: UUID) -> Component:
    return db.session.get_one(Component, component_id)


class FlashableException(Protocol):
    def as_flash_context(self) -> dict[str, str]: ...


class DependencyOrderException(Exception, FlashableException):
    def __init__(self, message: str, component: Component, depends_on_component: Component):
        super().__init__(message)
        self.message = message
        self.question = component
        self.depends_on_question = depends_on_component

    def as_flash_context(self) -> dict[str, str]:
        return {
            "message": self.message,
            "grant_id": str(self.question.form.section.collection.grant_id),  # Required for URL routing
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            # currently you can't depend on the outcome to a generic component (like a group)
            # so question continues to make sense here - we should review that naming if that
            # functionality changes
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
        }


class DataSourceItemReferenceDependencyException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        question_being_edited: Question,
        data_source_item_dependency_map: dict[Question, set[DataSourceItem]],
    ):
        super().__init__(message)
        self.message = message
        self.question_being_edited = question_being_edited
        self.data_source_item_dependency_map = data_source_item_dependency_map

    def as_flash_context(self) -> dict[str, str]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str]]:
        flash_contexts = []
        for dependent_question, data_source_items in self.data_source_item_dependency_map.items():
            flash_contexts.append(
                {
                    "message": self.message,
                    "question_id": str(dependent_question.id),
                    "question_text": dependent_question.text,
                    "depends_on_question_id": str(self.question_being_edited.id),
                    "depends_on_question_text": self.question_being_edited.text,
                    "depends_on_items_text": ", ".join(
                        data_source_item.label for data_source_item in data_source_items
                    ),
                }
            )
        return flash_contexts


# todo: we might want something more generalisable that checks all order dependencies across a form
#       but this gives us the specific result we want for the UX for now
def check_component_order_dependency(component: Component, swap_component: Component) -> None:
    for condition in component.conditions:
        if condition.managed and condition.managed.question_id == swap_component.id:
            raise DependencyOrderException(
                "You cannot move questions above answers they depend on", component, swap_component
            )

    for condition in swap_component.conditions:
        if condition.managed and condition.managed.question_id == component.id:
            raise DependencyOrderException(
                "You cannot move answers below questions that depend on them", swap_component, component
            )


def is_component_dependency_order_valid(component: Component, depends_on_component: Component) -> bool:
    return component.order > depends_on_component.order


# todo: when working generically with components this should dig in and check child components
#       a short term workaround might be to use _all_components but ideally this should
#       just expect nested components
def raise_if_question_has_any_dependencies(question: Question) -> Never | None:
    for target_question in question.form.questions:
        for condition in target_question.conditions:
            if condition.managed and condition.managed.question_id == question.id:
                raise DependencyOrderException(
                    "You cannot delete an answer that other questions depend on", target_question, question
                )
    return None


def raise_if_data_source_item_reference_dependency(
    question: Question, items_to_delete: Sequence[DataSourceItem]
) -> Never | None:
    data_source_item_dependency_map: dict[Question, set[DataSourceItem]] = {}
    for data_source_item in items_to_delete:
        for reference in data_source_item.references:
            dependent_question = reference.expression.question
            if dependent_question not in data_source_item_dependency_map:
                data_source_item_dependency_map[dependent_question] = set()
            data_source_item_dependency_map[dependent_question].add(data_source_item)

    if data_source_item_dependency_map:
        db.session.rollback()
        raise DataSourceItemReferenceDependencyException(
            "You cannot delete or change an option that other questions depend on.",
            question_being_edited=question,
            data_source_item_dependency_map=data_source_item_dependency_map,
        )
    return None


def move_component_up(component: Component) -> Component:
    swap_component = component.container.components[component.order - 1]
    check_component_order_dependency(component, swap_component)
    swap_elements_in_list_and_flush(component.container.components, component.order, swap_component.order)
    return component


def move_component_down(component: Component) -> Component:
    swap_component = component.container.components[component.order + 1]
    check_component_order_dependency(component, swap_component)
    swap_elements_in_list_and_flush(component.container.components, component.order, swap_component.order)
    return component


def update_question(
    question: Question,
    *,
    text: str,
    hint: str | None,
    name: str,
    items: list[str] | None = None,
    presentation_options: QuestionPresentationOptions | None = None,
) -> Question:
    question.text = text
    question.hint = hint
    question.name = name
    question.slug = slugify(text)
    question.presentation_options = presentation_options

    if items is not None:
        _update_data_source(question, items)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return question


def add_submission_event(
    submission: Submission, key: SubmissionEventKey, user: User, form: Form | None = None
) -> Submission:
    submission.events.append(SubmissionEvent(key=key, created_by=user, form=form))
    db.session.flush()
    return submission


def clear_submission_events(submission: Submission, key: SubmissionEventKey, form: Form | None = None) -> Submission:
    submission.events = [x for x in submission.events if not (x.key == key and (x.form == form if form else True))]
    db.session.flush()
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


def add_component_condition(component: Component, user: User, managed_expression: "ManagedExpression") -> Component:
    if not is_component_dependency_order_valid(component, managed_expression.referenced_question):
        raise DependencyOrderException(
            "Cannot add managed condition that depends on a later question",
            component,
            managed_expression.referenced_question,
        )

    expression = Expression.from_managed(managed_expression, user)
    component.expressions.append(expression)

    try:
        if (
            isinstance(managed_expression, BaseDataSourceManagedExpression)
            and managed_expression.referenced_question.data_source
        ):
            expression = _update_data_source_references(expression=expression, managed_expression=managed_expression)
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return component


def add_question_validation(question: Question, user: User, managed_expression: "ManagedExpression") -> Question:
    expression = Expression(
        statement=managed_expression.statement,
        context=managed_expression.model_dump(mode="json"),
        created_by=user,
        type=ExpressionType.VALIDATION,
        managed_name=managed_expression._key,
    )
    question.expressions.append(expression)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return question


def get_expression(expression_id: UUID) -> Expression:
    return db.session.get_one(Expression, expression_id)


def remove_question_expression(question: Question, expression: Expression) -> Question:
    question.expressions.remove(expression)
    db.session.flush()
    return question


def update_question_expression(expression: Expression, managed_expression: "ManagedExpression") -> Expression:
    expression.statement = managed_expression.statement
    expression.context = managed_expression.model_dump(mode="json")
    expression.managed_name = managed_expression._key

    if (
        isinstance(managed_expression, BaseDataSourceManagedExpression)
        and managed_expression.referenced_question.data_source
    ):
        expression = _update_data_source_references(expression=expression, managed_expression=managed_expression)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return expression


def delete_collection(collection: Collection) -> None:
    if collection.live_submissions:
        db.session.rollback()
        raise ValueError("Cannot delete collection with live submissions")

    db.session.delete(collection)
    db.session.flush()


def delete_form(form: Form) -> None:
    db.session.delete(form)
    form.section.forms = [f for f in form.section.forms if f.id != form.id]  # type: ignore[assignment]
    form.section.forms.reorder()  # Force all other forms to update their `order` attribute
    db.session.execute(text("SET CONSTRAINTS uq_form_order_section DEFERRED"))
    db.session.flush()


def delete_question(question: Question) -> None:
    raise_if_question_has_any_dependencies(question)
    db.session.delete(question)
    if question in question.form.questions:
        question.form.components.remove(question)
    question.form.components.reorder()
    db.session.execute(text("SET CONSTRAINTS uq_component_order_form DEFERRED"))
    db.session.flush()


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

    db.session.flush()
