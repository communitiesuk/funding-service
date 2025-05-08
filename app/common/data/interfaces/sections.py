from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Section
from app.extensions import db


def create_section(*, title: str, order: int, collection_schema_id: UUID) -> Section:
    """Create a new section."""
    section = Section(title=title, order=order, collection_schema_id=collection_schema_id)
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


def update_section(section: Section, *, title: str, order: int) -> Section:
    """Update an existing section."""
    section.title = title
    section.order = order

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section
