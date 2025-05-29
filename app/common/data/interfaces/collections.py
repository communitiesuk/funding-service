import copy

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import CollectionSchema, Form, Grant, Question, Section, Submission, User
from app.extensions import db


def create_collection_schema(*, name: str, user: User, grant: Grant, version: int = 1) -> CollectionSchema:
    schema = CollectionSchema(name=name, created_by=user, grant=grant, version=version)
    db.session.add(schema)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return schema


# should this be the submission, the question and the data to write
# plenty of questions about what if this is multiple questions or what its add another
# but this is a start
# I get the _sense_ the interface should deal with models and not helper wrappers
# for now assumes the model has been serialised for us, it would be to move that down to here as the interface should be consistent
def _submit_data(submission: Submission, question: Question, data: str):
    # I _think_ the default value isn't provided if its just been created - should look into if this is true even
    # after a flush

    # note should consider the cost of this as it gets _big_
    # could also use sql alvhemy mutable extension
    submission.data = copy.deepcopy(submission.data)
    submission.data[str(question.id)] = data
    db.session.flush()

    # only when we're doing the mark as complete part do we need to be writing
    # submission events


def _get_submission(id: UUID4) -> Submission:
    stmt = (
        select(Submission)
        .options(
            joinedload(CollectionSchema.sections)
            .joinedload(Section.forms)
            .joinedload(Form.questions)
            .selectinload(Question.questions)
        )
        .where(Submission.id == id)
    )
    result = db.session.execute(stmt).unique().scalar_one()
    return result


def _get_collection_schema(id: UUID4) -> CollectionSchema:
    stmt = (
        select(CollectionSchema)
        .options(
            joinedload(CollectionSchema.sections)
            .joinedload(Section.forms)
            .joinedload(Form.questions)
            .selectinload(Question.questions)
        )
        .where(CollectionSchema.id == id)
    )
    result = db.session.execute(stmt).unique().scalar_one()
    return result


def _get_submission(id: UUID4) -> Submission:
    stmt = (
        select(Submission)
        .options(
            joinedload(Submission.collection)
            .joinedload(CollectionSchema.sections)
            .joinedload(Section.forms)
            .joinedload(Form.questions)
            .selectinload(Question.questions)
        )
        .where(Submission.id == id)
    )
    return db.session.execute(stmt).unique().scalar_one()

    # joinedload(CollectionSchema.sections)
    # .selectinload(Section.forms)  # Load top-level forms
    # .selectinload(Form.child_forms)  # Load nested forms recursively (SQLAlchemy handles depth)
    # .selectinload(Form.questions),  # Load questions within nested forms

    # these are almost definitely not being applied

    # I suspect these aren't being applied
    # joinedload(CollectionSchema.sections)
    #     .selectinload(Section.forms)
    #     .selectinload(Form.questions)
    #     .selectinload(Question.questions)

    # .selectinload(Question.questions),  # Load nested questions recursively
    # selectinload(Section.forms)  # Need to specify path from Schema again for questions
    # .selectinload(Form.questions)  # Load top-level questions in top-level forms
    # .selectinload(Question.questions),  # Load nested questions recursively


def get_collection_schema(collection_id: UUID4) -> CollectionSchema:
    return db.session.get_one(CollectionSchema, collection_id)


def update_collection_schema(collection: CollectionSchema, *, name: str) -> CollectionSchema:
    collection.name = name
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return collection
