from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import CollectionSchema, Section
from app.extensions import db


def create_section(*, title: str, collection_schema: CollectionSchema) -> Section:
    """Create a new section."""
    section = Section(title=title, collection_schema_id=collection_schema.id)
    collection_schema.sections.append(section)
    db.session.add(section)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section


def get_section_by_id(section_id: UUID) -> Section:
    """Retrieve a section by its ID."""
    return db.session.get_one(Section, section_id)


def update_section(section: Section, *, title: str) -> Section:
    """Update an existing section."""
    section.title = title

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section


def swap_elements_in_list(containing_list: list[Any], index_a: int, index_b: int) -> list[Any]:
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
    return containing_list


def move_section_up(section: Section) -> Section:
    """Move a section up in the order, which means move it lower in the list."""
    list_index = section.order - 1  # convert from 1-based order to 0-based list index
    swap_elements_in_list(section.collection_schema.sections, list_index, list_index - 1)
    db.session.execute(text("SET CONSTRAINTS uq_section_order_collection_schema DEFERRED"))
    db.session.flush()

    return section


def move_section_down(section: Section) -> Section:
    """Move a section down in the order, which means move it higher in the list."""
    list_index = section.order - 1  # convert from 1-based order to 0-based list index
    swap_elements_in_list(section.collection_schema.sections, list_index, list_index + 1)
    db.session.execute(text("SET CONSTRAINTS uq_section_order_collection_schema DEFERRED"))
    db.session.flush()
    return section
