import pytest

from app.common.data.interfaces.collections import (
    create_collection_schema,
    create_form,
    create_section,
    get_collection_schema,
    get_form_by_id,
    get_section_by_id,
    move_form_down,
    move_form_up,
    move_section_down,
    move_section_up,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import CollectionSchema


def test_get_collection(db_session, factories):
    cs = factories.collection_schema.create()
    from_db = get_collection_schema(collection_id=cs.id)
    assert from_db is not None


def test_create_collection(db_session, factories):
    g = factories.grant.create()
    u = factories.user.create()
    collection = create_collection_schema(name="test collection", user=u, grant=g)
    assert collection is not None
    assert collection.id is not None
    assert collection.slug == "test-collection"

    from_db = db_session.get(CollectionSchema, collection.id)
    assert from_db is not None


def test_create_collection_name_is_unique_per_grant(db_session, factories):
    grants = factories.grant.create_batch(2)
    u = factories.user.create()

    # Check collection created initially
    create_collection_schema(name="test_collection", user=u, grant=grants[0])

    # Check same name in a different grant is allowed
    collection_same_name_different_grant = create_collection_schema(name="test_collection", user=u, grant=grants[1])
    assert collection_same_name_different_grant.id is not None

    # Check same name in the same grant is allowed with a different version
    collection_same_name_different_version = create_collection_schema(
        name="test_collection", user=u, grant=grants[0], version=2
    )
    assert collection_same_name_different_version.id is not None

    # Check same name in the same grant is not allowed with the same version
    with pytest.raises(DuplicateValueError):
        create_collection_schema(name="test_collection", user=u, grant=grants[0])


def test_get_section(db_session, factories):
    cs = factories.collection_schema.create()
    section = factories.section.create(collection_schema=cs)
    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 0


def test_create_section(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section", collection_schema=cs)
    assert section

    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 0

    section = create_section(title="test_section_2", collection_schema=cs)


def test_section_ordering(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section_1", collection_schema=cs)
    assert section
    assert section.order == 0

    section2 = create_section(title="test_section_2", collection_schema=cs)
    assert section2
    assert section2.order == 1


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

    assert section1.order == 0
    assert section2.order == 1

    # Move section 2 up
    move_section_up(section2)

    assert section1.order == 1
    assert section2.order == 0

    # Move section 2 down
    move_section_down(section2)

    assert section1.order == 0
    assert section2.order == 1


def test_get_form(db_session, factories):
    f = factories.form.create()
    from_db = get_form_by_id(form_id=f.id)
    assert from_db is not None


def test_create_form(db_session, factories):
    section = factories.section.create()
    form = create_form(title="Test Form", section=section)
    assert form is not None
    assert form.id is not None
    assert form.title == "Test Form"
    assert form.order == 0
    assert form.slug == "test-form"


def test_form_name_unique_in_section(db_session, factories):
    section = factories.section.create()
    form = create_form(title="test form", section=section)
    assert form

    with pytest.raises(DuplicateValueError):
        create_form(title="test form", section=section)


def test_move_form_up_down(db_session, factories):
    section = factories.section.create()
    form1 = factories.form.create(section=section)
    form2 = factories.form.create(section=section)

    assert form1
    assert form2

    assert form1.order == 0
    assert form2.order == 1

    # Move form 2 up
    move_form_up(form2)

    assert form1.order == 1
    assert form2.order == 0

    # Move form 2 down
    move_form_down(form2)

    assert form1.order == 0
    assert form2.order == 1
