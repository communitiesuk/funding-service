import uuid
from typing import TYPE_CHECKING, Any, Never, Protocol
from uuid import UUID

from sqlalchemy import ScalarResult, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.common.collections.types import AllAnswerTypes
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import (
    Collection,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
    Grant,
    Question,
    Section,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_user import User
from app.common.data.types import (
    ExpressionType,
    QuestionDataType,
    QuestionType,
    SubmissionEventKey,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.utils import slugify
from app.extensions import db

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


def create_collection(*, name: str, user: User, grant: Grant, version: int = 1) -> Collection:
    collection = Collection(name=name, created_by=user, grant=grant, version=version, slug=slugify(name))
    db.session.add(collection)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return collection


def get_collection(collection_id: UUID, version: int | None = None, with_full_schema: bool = False) -> Collection:
    """Get a collection by ID and optionally version.

    If you do not pass a version, it will retrieve the latest version (ie highest version number).

    Note: We may wish to change this behaviour to the latest 'published' version in the future, or some other logic.
    """
    options = []
    if with_full_schema:
        options.append(selectinload(Collection.sections).selectinload(Section.forms).selectinload(Form.questions))
    if version is None:
        return db.session.scalars(
            select(Collection)
            .where(Collection.id == collection_id)
            .order_by(Collection.version.desc())
            .options(*options)
            .limit(1)
        ).one()

    return db.session.get_one(Collection, [collection_id, version], options=options)


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


def get_all_submissions_with_mode_for_collection_with_full_schema(
    collection_id: UUID, submission_mode: SubmissionModeEnum
) -> ScalarResult[Submission]:
    """
    Use this function to get all submission data for a collection - it
    loads all the question/expression/user data at once to optimise
    performance and reduce the number of queries compared to looping
    through them all individually.
    """
    return db.session.scalars(
        select(Submission)
        .where(Submission.collection_id == collection_id)
        .where(Submission.mode == submission_mode)
        .options(
            joinedload(Submission.collection)
            .selectinload(Collection.sections)
            .selectinload(Section.forms)
            .selectinload(Form.questions)
            .selectinload(Question.expressions),
            selectinload(Submission.events),
            joinedload(Submission.created_by),
        )
    ).unique()


def get_submission(submission_id: UUID, with_full_schema: bool = False) -> Submission:
    options = []
    if with_full_schema:
        options.extend(
            [
                joinedload(Submission.collection)
                .selectinload(Collection.sections)
                .selectinload(Section.forms)
                .selectinload(Form.questions),
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
        status=SubmissionStatusEnum.NOT_STARTED,
    )
    db.session.add(submission)
    db.session.flush()
    return submission


def create_section(*, title: str, collection: Collection) -> Section:
    section = Section(title=title, collection_id=collection.id, slug=slugify(title))
    collection.sections.append(section)  # type: ignore[no-untyped-call]
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
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
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


# todo: when we get the form we should also fetch the questions to a certain depth to avoid them from being lazy loaded
def get_form_by_id(form_id: UUID, with_all_questions: bool = False) -> Form:
    options = []
    if with_all_questions:
        # todo: this will need refining again when we have different levels of grouped questions
        options.append(selectinload(Form.questions).joinedload(Question.expressions))
    return db.session.query(Form).options(*options).where(Form.id == form_id).one()


def create_form(*, title: str, section: Section) -> Form:
    form = Form(title=title, section_id=section.id, slug=slugify(title))
    section.forms.append(form)  # type: ignore[no-untyped-call]
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


def update_form(form: Form, *, title: str) -> Form:
    form.title = title
    form.slug = slugify(title)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


def _create_data_source(question: Question, items: list[str]) -> None:
    data_source = DataSource(id=uuid.uuid4(), question_id=question.id)
    db.session.add(data_source)

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

    new_choices = [
        existing_choices_map.get(
            slugify(choice),
            DataSourceItem(data_source_id=question.data_source.id, key=slugify(choice), label=choice),
        )
        for choice in items
    ]

    db.session.execute(text("SET CONSTRAINTS uq_data_source_id_order DEFERRED"))

    to_delete = [item for item in question.data_source.items if item not in new_choices]
    for item_to_delete in to_delete:
        db.session.delete(item_to_delete)

    question.data_source.items = new_choices
    question.data_source.items.reorder()  # type: ignore[attr-defined]

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise e


def create_question(
    form: Form = None,
    group: Question = None,
    *,
    text: str,
    hint: str,
    name: str,
    data_type: QuestionDataType,
    items: list[str] | None = None,
) -> Question:
    if form is None and group is None:
        raise ValueError("Specify either form or group")

    question = Question(
        text=text,
        form=form if form else None,
        parent=group if group else None,
        slug=slugify(text),
        hint=hint,
        name=name,
        data_type=data_type,
        type=QuestionType.QUESTION,
    )
    if form:
        form.questions.append(question)  # type: ignore[no-untyped-call]
    elif group:
        # todo: we can call this "children" if it helps the code read better - I like representing the the theory for now
        group.questions.append(question)  # type: ignore[no-untyped-call]
    db.session.add(question)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e

    if items is not None:
        _create_data_source(question, items)
        db.session.flush()

    return question


def create_group(form: Form,  parent_group: Question, *, name: str) -> Question:
    if form is None and parent_group is None:
        raise ValueError("Specify either form or parent_group")
    
    # todo: you probably want to have a user presentable name for the group (the text)
    #       and a data export name for the group (the name)
    group = Question(
        text=name, form=form if form else None, parent=parent_group if parent_group else None, slug=slugify(name), name=name, data_type=QuestionDataType.PAGE, type=QuestionType.GROUP
    )
    if form:
        form.questions.append(group)  # type: ignore[no-untyped-call]
    elif parent_group:
        parent_group.questions.append(group)  # type: ignore[no-untyped-call]
    db.session.add(group)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e

    return group


def get_question_by_id(question_id: UUID) -> Question:
    return db.session.get_one(Question, question_id)


class FlashableException(Protocol):
    def as_flash_context(self) -> dict[str, str]: ...


class DependencyOrderException(Exception, FlashableException):
    def __init__(self, message: str, question: Question, depends_on_question: Question):
        super().__init__(message)
        self.message = message
        self.question = question
        self.depends_on_question = depends_on_question

    def as_flash_context(self) -> dict[str, str]:
        return {
            "message": self.message,
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
        }


# todo: we might want something more generalisable that checks all order dependencies across a form
#       but this gives us the specific result we want for the UX for now
def check_question_order_dependency(question: Question, swap_question: Question) -> None:
    get_all_parents_ids = lambda q: [q.id] + (get_all_parents_ids(q.parent) if q.parent else [])

    def get_all_questions(ql: list["Question"]) -> list["Question"]:
        questions = []
        for question in ql:
            if question.is_group:

                # fixme: get question includes groups for now, this should all be managed consistently from helpers
                questions.extend([question, *get_all_questions(question.questions)])
            else:
                questions.append(question)
        return questions

    question_flat_questions = get_all_questions([question])
    swap_question_flat_questions = get_all_questions([swap_question])

    # this will be getting to be a very expensive check
    for q in question_flat_questions:
        for condition in q.conditions:
            for swap_q in swap_question_flat_questions:
                    if condition.managed and condition.managed.question_id == swap_q.id:
                        # if condition.managed and condition.managed.question_id == swap_question.id:
                        # if condition.managed and condition.managed.question_id in get_all_parents_ids(swap_question):
                        raise DependencyOrderException(
                            "You cannot move questions above answers they depend on", question, swap_question
                        )

    for swap_q in swap_question_flat_questions:
        for condition in swap_q.conditions:
            for q in question_flat_questions:
                if condition.managed and condition.managed.question_id == q.id:
                    raise DependencyOrderException(
                        "You cannot move answers below questions that depend on them", swap_question, question
                    )


def is_question_dependency_order_valid(question: Question, depends_on_question: Question) -> bool:
    def get_all_questions(ql: list["Question"]) -> list["Question"]:
        questions = []
        for question in ql:
            if question.is_group:

                # fixme: get question includes groups for now, this should all be managed consistently from helpers
                questions.extend([question, *get_all_questions(question.questions)])
            else:
                questions.append(question)
        return questions
    
    # this is almost definitely silly
    flattened_questions = get_all_questions(question.belongs_to_form.questions)

    return flattened_questions.index(question) > flattened_questions.index(depends_on_question)


def raise_if_question_has_any_dependencies(question: Question) -> Never | None:

    def get_all_questions(ql: list["Question"]) -> list["Question"]:
        questions = []
        for question in ql:
            if question.is_group:

                # fixme: get question includes groups for now, this should all be managed consistently from helpers
                questions.extend([question, *get_all_questions(question.questions)])
            else:
                questions.append(question)
        return questions
    
    # fixme: just changing this doesn't actually make sense it should go through all of the questions
    #        there should be a default way of going through all questions flat - its likely a property on the form
    for target_question in get_all_questions(question.belongs_to_form.questions):
        for condition in target_question.conditions:
            if condition.managed and condition.managed.question_id == question.id:
                raise DependencyOrderException(
                    "You cannot delete an answer that other questions depend on", target_question, question
                )
    return None


def move_question_up(question: Question) -> Question:
    # todo: a generic way of referencing this concept, as well as to a flat representation of all of the questions in a form
    parent = question.parent or question.form
    swap_question = parent.questions[question.order - 1]
    check_question_order_dependency(question, swap_question)
    swap_elements_in_list_and_flush(parent.questions, question.order, swap_question.order)
    return question


def move_question_down(question: Question) -> Question:
    parent = question.parent or question.form
    swap_question = parent.questions[question.order + 1]
    check_question_order_dependency(question, swap_question)
    swap_elements_in_list_and_flush(parent.questions, question.order, swap_question.order)
    return question


def update_question(
    question: Question, *, text: str, hint: str | None, name: str, items: list[str] | None = None
) -> Question:
    question.text = text
    question.hint = hint
    question.name = name
    question.slug = slugify(text)

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


def add_question_condition(question: Question, user: User, managed_expression: "ManagedExpression") -> Question:
    if not is_question_dependency_order_valid(question, managed_expression.referenced_question):
        raise DependencyOrderException(
            "Cannot add managed condition that depends on a later question",
            question,
            managed_expression.referenced_question,
        )

    expression = Expression.from_managed(managed_expression, user)
    question.expressions.append(expression)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return question


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
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return expression
