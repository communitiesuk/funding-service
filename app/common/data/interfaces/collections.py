from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import (
    Collection,
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
    SubmissionEventKey,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.utils import slugify
from app.extensions import db

if TYPE_CHECKING:
    from app.common.expressions.managed import BaseExpression


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


def update_submission_data(submission: Submission, question: Question, data: BaseModel) -> Submission:
    submission.data[str(question.id)] = data.model_dump()
    db.session.flush()
    return submission


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


def get_form_by_id(form_id: UUID) -> Form:
    return db.session.get_one(Form, form_id)


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


def update_form(form: Form, *, title: str) -> Form:
    form.title = title
    form.slug = slugify(title)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


def create_question(form: Form, *, text: str, hint: str, name: str, data_type: QuestionDataType) -> Question:
    question = Question(text=text, form_id=form.id, slug=slugify(text), hint=hint, name=name, data_type=data_type)
    form.questions.append(question)
    db.session.add(question)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return question


def get_question_by_id(question_id: UUID) -> Question:
    return db.session.get_one(Question, question_id)


def move_question_up(question: Question) -> Question:
    swap_elements_in_list_and_flush(question.form.questions, question.order, question.order - 1)
    return question


def move_question_down(question: Question) -> Question:
    swap_elements_in_list_and_flush(question.form.questions, question.order, question.order + 1)
    return question


def update_question(question: Question, *, text: str, hint: str | None, name: str) -> Question:
    question.text = text
    question.hint = hint
    question.name = name
    question.slug = slugify(text)

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


def add_question_condition(question: Question, user: User, managed_expression: "BaseExpression") -> Question:
    expression = Expression(
        statement=managed_expression.statement,
        context=managed_expression.model_dump(mode="json"),
        created_by=user,
        type=ExpressionType.CONDITION,
    )
    question.expressions.append(expression)
    db.session.flush()
    return question


def add_question_validation(question: Question, user: User, managed_expression: "BaseExpression") -> Question:
    expression = Expression(
        statement=managed_expression.statement,
        context=managed_expression.model_dump(mode="json"),
        created_by=user,
        type=ExpressionType.VALIDATION,
    )
    question.expressions.append(expression)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return question


def remove_question_expression(question: Question, expression: Expression) -> Question:
    question.expressions.remove(expression)
    db.session.flush()
    return question


def update_question_expression(expression: Expression, managed_expression: "BaseExpression") -> Expression:
    expression.statement = managed_expression.statement
    expression.context = managed_expression.model_dump(mode="json")
    db.session.flush()
    return expression
