"""
This module contains temporary functions that are used to support the scaffolding of the core platform functionality.

We anticipate that they should not be used by any of the real domains themselves (eg apply, assess, monitor), but are
required to support the technical build-out of the platform.

This file should be removed once the scaffolding is complete and some domain skins are in place.

The only place that should import from here is the `app.developers` package.
"""

from uuid import UUID

from sqlalchemy import select, text

from app.common.data.interfaces.collections import DependencyOrderException, depends_on_question
from app.common.data.models import (
    Collection,
    Form,
    Grant,
    Question,
    Section,
    Submission,
)
from app.common.data.models_user import User
from app.extensions import db


def delete_submissions_created_by_user(*, grant_id: UUID, created_by_id: UUID) -> None:
    submissions = (
        db.session.query(Submission)
        .join(Collection)
        .where(
            Collection.grant_id == grant_id,
            Submission.created_by_id == created_by_id,
        )
        .all()
    )

    for submission in submissions:
        db.session.delete(submission)
    db.session.flush()


def delete_grant(grant_id: UUID) -> None:
    # Not optimised; do not lift+shift unedited.
    grant = db.session.query(Grant).where(Grant.id == grant_id).one()
    db.session.delete(grant)
    db.session.flush()


def delete_collection(collection_id: UUID) -> None:
    collection = db.session.query(Collection).where(Collection.id == collection_id).one()
    db.session.delete(collection)
    db.session.flush()


def delete_section(section: Section) -> None:
    db.session.delete(section)
    section.collection.sections.reorder()
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
    )
    db.session.flush()


def delete_form(form: Form) -> None:
    db.session.delete(form)
    form.section.forms.reorder()
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
    )
    db.session.flush()


def delete_question(question: Question) -> None:
    depends_on_this_question = depends_on_question(question)
    if depends_on_this_question:
        raise DependencyOrderException(
            "You cannot delete an answer that other questions depend on", depends_on_this_question, question
        )
    db.session.delete(question)
    question.form.questions.reorder()
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
    )
    db.session.flush()


def get_submission_by_collection_and_user(collection: Collection, user: "User") -> Submission | None:
    return db.session.scalar(
        select(Submission).where(Submission.collection == collection, Submission.created_by == user)
    )
