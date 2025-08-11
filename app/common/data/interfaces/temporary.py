"""
This module contains temporary functions that are used to support the scaffolding of the core platform functionality.

We anticipate that they should not be used by any of the real domains themselves (eg apply, assess, monitor), but are
required to support the technical build-out of the platform.

This file should be removed once the scaffolding is complete and some domain skins are in place.

The only place that should import from here is the `app.developers` package.
"""

from uuid import UUID

from sqlalchemy import select, text

from app.common.data.interfaces.collections import create_section, raise_if_question_has_any_dependencies
from app.common.data.models import (
    Collection,
    Form,
    Grant,
    Question,
    Section,
    Submission,
)
from app.common.data.models_user import User
from app.constants import DEFAULT_SECTION_NAME
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
    # remove the instance from its collection specifically, which triggers reordering of all other sections
    # correctly.
    # todo: when/if this becomes a non-temporary interface, TEST THOROUGHLY. The OrderingList we're using for this
    # definitely has a few quirks.
    collection = section.collection
    db.session.delete(section)
    if section in section.collection.sections:
        section.collection.sections.remove(section)
    section.collection.sections.reorder()
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_component_order_form DEFERRED")
    )

    # If we're deleting the last section, automatically add the default section back. We should never end up with a
    # collection that has zero sections.
    if len(collection.sections) == 0:
        create_section(title=DEFAULT_SECTION_NAME, collection=collection)

    db.session.flush()


def delete_form(form: Form) -> None:
    # remove the instance from its collection specifically, which triggers reordering of all other sections
    # correctly.
    # todo: when/if this becomes a non-temporary interface, TEST THOROUGHLY. The OrderingList we're using for this
    # definitely has a few quirks.
    db.session.delete(form)
    if form in form.section.forms:
        form.section.forms.remove(form)
    form.section.forms.reorder()
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_component_order_form DEFERRED")
    )
    db.session.flush()


def delete_question(question: Question) -> None:
    raise_if_question_has_any_dependencies(question)
    # remove the instance from its collection specifically, which triggers reordering of all other sections
    # correctly.
    # todo: when/if this becomes a non-temporary interface, TEST THOROUGHLY. The OrderingList we're using for this
    # definitely has a few quirks.
    db.session.delete(question)
    if question in question.container.components:
        question.container.components.remove(question)
    question.container.components.reorder()
    db.session.execute(
        text("SET CONSTRAINTS uq_section_order_collection, uq_form_order_section, uq_component_order_form DEFERRED")
    )
    db.session.flush()


def get_submission_by_collection_and_user(collection: Collection, user: "User") -> Submission | None:
    return db.session.scalar(
        select(Submission).where(Submission.collection == collection, Submission.created_by == user)
    )
