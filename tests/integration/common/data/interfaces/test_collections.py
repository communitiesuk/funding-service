import pytest

from app.common.data.interfaces.collections import (
    add_collection_metadata,
    clear_form_metadata,
    create_collection_schema,
    create_form,
    create_question,
    create_section,
    get_collection,
    get_collection_schema,
    get_form_by_id,
    get_question_by_id,
    get_section_by_id,
    move_form_down,
    move_form_up,
    move_question_down,
    move_question_up,
    move_section_down,
    move_section_up,
    update_collection_data,
    update_question,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import CollectionSchema
from app.common.data.types import MetadataEventKey, QuestionDataType
from app.common.helpers.collections import TextSingleLine


def test_get_collection_schema(db_session, factories):
    cs = factories.collection_schema.create()
    from_db = get_collection_schema(schema_id=cs.id)
    assert from_db is not None


def test_get_collection_schema_version(db_session, factories):
    cs = factories.collection_schema.create()
    _ = factories.collection_schema.create(id=cs.id, version=2)

    from_db = get_collection_schema(schema_id=cs.id, version=1)
    from_db_v2 = get_collection_schema(schema_id=cs.id, version=2)
    assert from_db.version == 1
    assert from_db_v2.version == 2


def test_get_collection_schema_version_latest_by_default(db_session, factories):
    cs = factories.collection_schema.create()
    _ = factories.collection_schema.create(id=cs.id, version=2)
    _ = factories.collection_schema.create(id=cs.id, version=3)
    _ = factories.collection_schema.create(id=cs.id, version=4)

    from_db = get_collection_schema(schema_id=cs.id)
    assert from_db.version == 4


def test_create_collection_schema(db_session, factories):
    g = factories.grant.create()
    u = factories.user.create()
    collection = create_collection_schema(name="test collection", user=u, grant=g)
    assert collection is not None
    assert collection.id is not None
    assert collection.slug == "test-collection"

    from_db = db_session.get(CollectionSchema, [collection.id, collection.version])
    assert from_db is not None


def test_create_collection_schema_name_is_unique_per_grant(db_session, factories):
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


def test_get_collection(db_session, factories):
    collection = factories.collection.create()
    from_db = get_collection(collection_id=collection.id)
    assert from_db is not None


def test_get_collection_with_full_schema(db_session, factories, track_sql_queries):
    collection = factories.collection.create()
    collection_id = collection.id
    sections = factories.section.create_batch(3, collection_schema=collection.collection_schema)
    for section in sections:
        forms = factories.form.create_batch(3, section=section)
        for form in forms:
            factories.question.create_batch(3, form=form)

    with track_sql_queries() as queries:
        from_db = get_collection(collection_id=collection_id, with_full_schema=True)
    assert from_db is not None

    # Expected queries:
    # * Load the collection with the schema attached
    # * Load the sections
    # * Load the forms
    # * Load the question
    assert len(queries) == 4

    # Iterate over all the related models; check that no further SQL queries are emitted. The count is just a noop.
    count = 0
    with track_sql_queries() as queries:
        for s in from_db.collection_schema.sections:
            for f in s.forms:
                for _q in f.questions:
                    count += 1

    assert queries == []


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
    section = create_section(title="test_section", schema=cs)
    assert section

    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 0

    section = create_section(title="test_section_2", schema=cs)


def test_section_ordering(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section_1", schema=cs)
    assert section
    assert section.order == 0

    section2 = create_section(title="test_section_2", schema=cs)
    assert section2
    assert section2.order == 1


def test_section_name_unique_in_collection(db_session, factories):
    cs = factories.collection_schema.create()
    section = create_section(title="test_section", schema=cs)
    assert section

    with pytest.raises(DuplicateValueError):
        create_section(title="test_section", schema=cs)


def test_move_section_up_down(db_session, factories):
    cs = factories.collection_schema.create()
    section1 = create_section(title="test_section_1", schema=cs)
    section2 = create_section(title="test_section_2", schema=cs)
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


def test_get_question(db_session, factories):
    q = factories.question.create()
    from_db = get_question_by_id(question_id=q.id)
    assert from_db is not None


def test_create_question(db_session, factories):
    form = factories.form.create()
    question = create_question(
        form=form,
        text="Test Question",
        hint="Test Hint",
        name="Test Question Name",
        data_type=QuestionDataType.TEXT_MULTI_LINE,
    )
    assert question is not None
    assert question.id is not None
    assert question.text == "Test Question"
    assert question.hint == "Test Hint"
    assert question.name == "Test Question Name"
    assert question.data_type == QuestionDataType.TEXT_MULTI_LINE
    assert question.order == 0
    assert question.slug == "test-question"


def test_update_question(db_session, factories):
    form = factories.form.create()
    question = create_question(
        form=form,
        text="Test Question",
        hint="Test Hint",
        name="Test Question Name",
        data_type=QuestionDataType.INTEGER,
    )
    assert question is not None

    updated_question = update_question(
        question=question,
        text="Updated Question",
        hint="Updated Hint",
        name="Updated Question Name",
    )

    assert updated_question.text == "Updated Question"
    assert updated_question.hint == "Updated Hint"
    assert updated_question.name == "Updated Question Name"
    assert updated_question.data_type == QuestionDataType.INTEGER
    assert updated_question.slug == "updated-question"


def test_move_question_up_down(db_session, factories):
    form = factories.form.create()
    q1 = factories.question.create(form=form)
    q2 = factories.question.create(form=form)
    q3 = factories.question.create(form=form)

    assert q1
    assert q2
    assert q3

    assert q1.order == 0
    assert q2.order == 1
    assert q3.order == 2

    move_question_up(q2)

    assert q1.order == 1
    assert q2.order == 0
    assert q3.order == 2

    move_question_down(q1)

    assert q1.order == 2
    assert q2.order == 0
    assert q3.order == 1


def test_update_collection_data(db_session, factories):
    question = factories.question.build()
    collection = factories.collection.build(collection_schema=question.form.section.collection_schema)

    assert str(question.id) not in collection.data

    data = TextSingleLine("User submitted data")
    updated_collection = update_collection_data(collection, question, data)

    assert updated_collection.data[str(question.id)] == "User submitted data"


def test_add_collection_metadata(db_session, factories):
    user = factories.user.build()
    collection = factories.collection.build()
    db_session.add(collection)

    add_collection_metadata(collection=collection, user=user, event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED)

    # pull it back out of the database to also check all of the serialisation/ enums are mapped appropriately
    from_db = get_collection(collection.id, with_full_schema=True)

    assert len(from_db.collection_metadata) == 1
    assert from_db.collection_metadata[0].event_key == MetadataEventKey.FORM_RUNNER_FORM_COMPLETED


def test_remove_metadata_for_a_key(db_session, factories):
    collection = factories.collection.build()
    section = factories.section.build(collection_schema=collection.collection_schema)
    form_one = factories.form.build(section=section)
    form_two = factories.form.build(section=section)

    add_collection_metadata(
        collection=collection, user=collection.created_by, event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED
    )
    add_collection_metadata(
        collection=collection, user=collection.created_by, event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED
    )

    # clears all keys of type
    clear_form_metadata(collection=collection, event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED)

    assert collection.collection_metadata == []

    # clears only a specific forms
    add_collection_metadata(
        collection=collection,
        user=collection.created_by,
        event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED,
        form=form_one,
    )
    add_collection_metadata(
        collection=collection,
        user=collection.created_by,
        event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED,
        form=form_two,
    )

    clear_form_metadata(collection=collection, event_key=MetadataEventKey.FORM_RUNNER_FORM_COMPLETED, form=form_one)

    assert len(collection.collection_metadata) == 1
    assert collection.collection_metadata[0].form == form_two


def test_get_collection_schema_with_full_schema(db_session, factories, track_sql_queries):
    schema = factories.collection_schema.create()
    sections = factories.section.create_batch(3, collection_schema=schema)
    for section in sections:
        forms = factories.form.create_batch(3, section=section)
        for form in forms:
            factories.question.create_batch(3, form=form)

    with track_sql_queries() as queries:
        from_db = get_collection_schema(schema_id=schema.id, with_full_schema=True)
    assert from_db is not None

    # Expected queries:
    # * Initial queries for schema and user
    # * Load the sections
    # * Load the forms
    # * Load the question
    assert len(queries) == 5

    # No additional queries when inspecting the ORM model
    count = 0
    with track_sql_queries() as queries:
        for s in from_db.sections:
            for f in s.forms:
                for _q in f.questions:
                    count += 1

    assert queries == []
