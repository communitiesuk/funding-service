from typing import Any
from uuid import UUID

from pydantic import UUID4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.utils import slugify
from app.common.data.models import CollectionSchema, Form, Grant, Question, Section, User
from app.extensions import db


def create_collection_schema(*, name: str, user: User, grant: Grant, version: int = 1) -> CollectionSchema:
    schema = CollectionSchema(name=name, created_by=user, grant=grant, version=version, slug=slugify(name))
    db.session.add(schema)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return schema


def get_collection_schema(collection_id: UUID4) -> CollectionSchema:
    return db.session.get_one(CollectionSchema, collection_id)


def update_collection_schema(collection: CollectionSchema, *, name: str) -> CollectionSchema:
    collection.name = name
    collection.slug = slugify(name)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return collection


def create_section(*, title: str, collection_schema: CollectionSchema) -> Section:
    section = Section(title=title, collection_schema_id=collection_schema.id, slug=slugify(title))
    collection_schema.sections.append(section)
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
    db.session.execute(text("SET CONSTRAINTS uq_section_order_collection_schema, uq_form_order_section DEFERRED"))
    db.session.flush()
    return containing_list


def move_section_up(section: Section) -> Section:
    """Move a section up in the order, which means move it lower in the list."""
    swap_elements_in_list_and_flush(section.collection_schema.sections, section.order, section.order - 1)

    return section


def move_section_down(section: Section) -> Section:
    """Move a section down in the order, which means move it higher in the list."""
    swap_elements_in_list_and_flush(section.collection_schema.sections, section.order, section.order + 1)
    return section


def get_form_by_id(form_id: UUID4) -> Form:
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


def create_question(form: Form, *, text: str, hint: str) -> Question:
    question = Question(text=text, form_id=form.id, slug=slugify(text), hint=hint)
    form.questions.append(question)
    db.session.add(question)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return question


def get_question_by_id(question_id: UUID4) -> Question:
    return db.session.get_one(Question, question_id)
