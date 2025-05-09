import pytest

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.sections import create_section, get_section_by_id, move_section_down, move_section_up


def test_get_section(db_session, factories):
    cs = factories.collection_schema.create()
    section = factories.section.create(collection_schema=cs)
    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 1


def test_create_section(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section", collection_schema=cs)
    assert section

    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 1

    section = create_section(title="test_section_2", collection_schema=cs)


def test_section_ordering(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section_1", collection_schema=cs)
    assert section
    assert section.order == 1

    section2 = create_section(title="test_section_2", collection_schema=cs)
    assert section2
    assert section2.order == 2


def test_section_name_unique_in_collection(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section", collection_schema=cs)
    assert section

    with pytest.raises(DuplicateValueError):
        create_section(title="test_section", collection_schema=cs)


def test_move_section_up_down(db_session, factories):
    cs = factories.collection_schema.create()
    section1 = create_section(title="test_section_1", collection_schema=cs)
    section2 = create_section(title="test_section_2", collection_schema=cs)
    assert section1
    assert section2

    assert section1.order == 1
    assert section2.order == 2

    # Move section 2 up
    move_section_up(section2)

    assert section1.order == 2
    assert section2.order == 1

    # Move section 2 down
    move_section_down(section2)

    assert section1.order == 1
    assert section2.order == 2
