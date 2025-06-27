"""
This module contains temporary functions that are used to support the scaffolding of the core platform functionality.

We anticipate that they should not be used by any of the real domains themselves (eg apply, assess, monitor), but are
required to support the technical build-out of the platform.

This file should be removed once the scaffolding is complete and some domain skins are in place.

The only place that should import from here is the `app.developers` package.
"""

from uuid import UUID

from sqlalchemy import text

from app.common.data.models import (
    Collection,
    Form,
    Grant,
    Section,
    Submission,
)
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


def delete_section(section_id: UUID, collection_id: UUID) -> None:
    collection = db.session.query(Collection).where(Collection.id == collection_id).one()
    section = next(section for section in collection.sections if section.id == section_id)

    db.session.delete(section)
    collection.sections.remove(section)

    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
    )
    db.session.flush()


def delete_form(form_id: UUID, section_id: UUID) -> None:
    section = db.session.query(Section).where(Section.id == section_id).one()
    form = next(form for form in section.forms if form.id == form_id)

    db.session.delete(form)
    section.forms.remove(form)

    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
    )
    db.session.flush()


def delete_question(question_id: UUID, form_id: UUID) -> None:
    form = db.session.query(Form).where(Form.id == form_id).one()
    question = next(question for question in form.questions if question.id == question_id)

    db.session.delete(question)
    form.questions.remove(question)
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_question_order_form DEFERRED")
    )
    db.session.flush()
