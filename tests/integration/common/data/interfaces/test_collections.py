import uuid

import pytest
from sqlalchemy.exc import NoResultFound

from app.common.collections.types import TextSingleLine
from app.common.data.interfaces.collections import (
    DependencyOrderException,
    add_question_condition,
    add_question_validation,
    add_submission_event,
    clear_submission_events,
    create_collection,
    create_form,
    create_question,
    create_section,
    get_collection,
    get_expression,
    get_form_by_id,
    get_question_by_id,
    get_section_by_id,
    get_submission,
    move_form_down,
    move_form_up,
    move_question_down,
    move_question_up,
    move_section_down,
    move_section_up,
    raise_if_question_has_any_dependencies,
    remove_question_expression,
    update_question,
    update_question_expression,
    update_submission_data,
)
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Collection, DataSourceItem, Expression
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType, SubmissionEventKey
from app.common.expressions.managed import GreaterThan, LessThan


def test_get_collection(db_session, factories):
    collection = factories.collection.create()
    from_db = get_collection(collection_id=collection.id)
    assert from_db is not None


def test_get_collection_version(db_session, factories):
    collection = factories.collection.create()
    _ = factories.collection.create(id=collection.id, version=2)

    from_db = get_collection(collection_id=collection.id, version=1)
    from_db_v2 = get_collection(collection_id=collection.id, version=2)
    assert from_db.version == 1
    assert from_db_v2.version == 2


def test_get_collection_version_latest_by_default(db_session, factories):
    collection = factories.collection.create()
    _ = factories.collection.create(id=collection.id, version=2)
    _ = factories.collection.create(id=collection.id, version=3)
    _ = factories.collection.create(id=collection.id, version=4)

    from_db = get_collection(collection_id=collection.id)
    assert from_db.version == 4


def test_create_collection(db_session, factories):
    g = factories.grant.create()
    u = factories.user.create()
    collection = create_collection(name="test collection", user=u, grant=g)
    assert collection is not None
    assert collection.id is not None
    assert collection.slug == "test-collection"

    from_db = db_session.get(Collection, [collection.id, collection.version])
    assert from_db is not None


def test_create_collection_name_is_unique_per_grant(db_session, factories):
    grants = factories.grant.create_batch(2)
    u = factories.user.create()

    # Check collection created initially
    create_collection(name="test_collection", user=u, grant=grants[0])

    # Check same name in a different grant is allowed
    collection_same_name_different_grant = create_collection(name="test_collection", user=u, grant=grants[1])
    assert collection_same_name_different_grant.id is not None

    # Check same name in the same grant is allowed with a different version
    collection_same_name_different_version = create_collection(
        name="test_collection", user=u, grant=grants[0], version=2
    )
    assert collection_same_name_different_version.id is not None

    # Check same name in the same grant is not allowed with the same version
    with pytest.raises(DuplicateValueError):
        create_collection(name="test_collection", user=u, grant=grants[0])


def test_get_submission(db_session, factories):
    submission = factories.submission.create()
    from_db = get_submission(submission_id=submission.id)
    assert from_db is not None


def test_get_submission_with_full_schema(db_session, factories, track_sql_queries):
    submission = factories.submission.create()
    submission_id = submission.id
    sections = factories.section.create_batch(3, collection=submission.collection)
    for section in sections:
        forms = factories.form.create_batch(3, section=section)
        for form in forms:
            factories.question.create_batch(3, form=form)

    with track_sql_queries() as queries:
        from_db = get_submission(submission_id=submission_id, with_full_schema=True)
    assert from_db is not None

    # Expected queries:
    # * Load the collection with the nested relationships attached
    # * Load the sections
    # * Load the forms
    # * Load the question
    assert len(queries) == 4

    # Iterate over all the related models; check that no further SQL queries are emitted. The count is just a noop.
    count = 0
    with track_sql_queries() as queries:
        for s in from_db.collection.sections:
            for f in s.forms:
                for _q in f.questions:
                    count += 1

    assert queries == []


def test_get_section(db_session, factories):
    collection = factories.collection.create()
    section = factories.section.create(collection=collection)
    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 0


def test_create_section(db_session, factories):
    collection = factories.collection.create()
    section = create_section(title="test_section", collection=collection)
    assert section

    from_db = get_section_by_id(section.id)
    assert from_db is not None
    assert from_db.id == section.id
    assert from_db.title == section.title
    assert from_db.order == 0

    section = create_section(title="test_section_2", collection=collection)


def test_section_ordering(db_session, factories):
    collection = factories.collection.create()
    section = create_section(title="test_section_1", collection=collection)
    assert section
    assert section.order == 0

    section2 = create_section(title="test_section_2", collection=collection)
    assert section2
    assert section2.order == 1


def test_section_name_unique_in_collection(db_session, factories):
    collection = factories.collection.create()
    section = create_section(title="test_section", collection=collection)
    assert section

    with pytest.raises(DuplicateValueError):
        create_section(title="test_section", collection=collection)


def test_move_section_up_down(db_session, factories):
    collection = factories.collection.create()
    section1 = create_section(title="test_section_1", collection=collection)
    section2 = create_section(title="test_section_2", collection=collection)
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


def test_get_form(db_session, factories, track_sql_queries):
    form = factories.form.create()

    # fetching the form directly
    from_db = get_form_by_id(form_id=form.id)
    assert from_db.id == form.id


def test_get_form_with_all_questions(db_session, factories, track_sql_queries):
    form = factories.form.create()
    question_one = factories.question.create(form=form)
    question_two = factories.question.create(form=form)
    factories.expression.create_batch(5, question=question_one, type=ExpressionType.CONDITION, statement="")
    factories.expression.create_batch(5, question=question_two, type=ExpressionType.CONDITION, statement="")

    # fetching the form and eagerly loading all questions and their expressions
    from_db = get_form_by_id(form_id=form.id, with_all_questions=True)

    # check we're not sending off more round trips to the database when interacting with the ORM
    count = 0
    with track_sql_queries() as queries:
        for q in from_db.questions:
            for _e in q.expressions:
                count += 1

    assert count == 10 and queries == []


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


class TestCreateQuestion:
    @pytest.mark.parametrize(
        "question_type",
        [
            QuestionDataType.TEXT_SINGLE_LINE,
            QuestionDataType.EMAIL,
            QuestionDataType.TEXT_MULTI_LINE,
            QuestionDataType.INTEGER,
            QuestionDataType.URL,
        ],
    )
    def test_simple_types(self, db_session, factories, question_type):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=question_type,
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == question_type
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is None

    def test_yes_no(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.YES_NO,
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == QuestionDataType.YES_NO
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is None

    def test_radios(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.RADIOS,
            items=["one", "two", "three"],
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == QuestionDataType.RADIOS
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is not None
        assert [item.key for item in question.data_source.items] == ["one", "two", "three"]

    def test_break_if_new_question_types_added(self):
        assert len(QuestionDataType) == 7, "Add a new test above if adding a new question type"


class TestUpdateQuestion:
    @pytest.mark.parametrize(
        "question_type",
        [
            QuestionDataType.TEXT_SINGLE_LINE,
            QuestionDataType.EMAIL,
            QuestionDataType.TEXT_MULTI_LINE,
            QuestionDataType.INTEGER,
        ],
    )
    def test_simple_types(self, db_session, factories, question_type):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=question_type,
        )
        assert question is not None
        assert question.data_source is None

        updated_question = update_question(
            question=question,
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == question_type
        assert updated_question.slug == "updated-question"
        assert updated_question.data_source is None

    def test_yes_no(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.YES_NO,
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
        assert updated_question.data_type == QuestionDataType.YES_NO
        assert updated_question.slug == "updated-question"

    def test_radios(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.RADIOS,
            items=["option 1", "option 2", "option 3"],
        )
        assert question is not None
        assert question.data_source_items == "option 1\noption 2\noption 3"
        item_ids = [item.id for item in question.data_source.items]

        updated_question = update_question(
            question=question,
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
            items=["option 3", "option 4", "option-1"],
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == QuestionDataType.RADIOS
        assert updated_question.slug == "updated-question"
        assert updated_question.data_source_items == "option 3\noption 4\noption-1"

        # Test that data source item IDs for existing/updated items are retained; new options are created.
        assert updated_question.data_source.items[0].id == item_ids[2]
        assert updated_question.data_source.items[1].id not in item_ids
        assert updated_question.data_source.items[2].id == item_ids[0]

        # The dropped item has been deleted
        assert db_session.get(DataSourceItem, item_ids[1]) is None

    def test_break_if_new_question_types_added(self):
        assert len(QuestionDataType) == 7, "Add a new test above if adding a new question type"


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


def test_move_question_with_dependencies(db_session, factories):
    form = factories.form.create()
    user = factories.user.create()
    q1, q2 = factories.question.create_batch(2, form=form)
    q3 = factories.question.create(
        form=form,
        expressions=[Expression.from_managed(GreaterThan(question_id=q2.id, minimum_value=3000), user)],
    )

    # q3 can't move above its dependency q2
    with pytest.raises(DependencyOrderException) as e:
        move_question_up(q3)
    assert e.value.question == q3  # ty: ignore[unresolved-attribute]
    assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

    # q2 can't move below q3 which depends on it
    with pytest.raises(DependencyOrderException) as e:
        move_question_down(q2)
    assert e.value.question == q3  # ty: ignore[unresolved-attribute]
    assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

    # q1 can freely move up and down as it has no dependencies
    move_question_down(q1)
    move_question_down(q1)
    move_question_up(q1)
    move_question_up(q1)

    # q2 can move up as q3 can still depend on it
    move_question_up(q2)


def test_raise_if_question_has_any_dependencies(db_session, factories):
    form = factories.form.create()
    user = factories.user.create()
    q1 = factories.question.create(form=form)
    q2 = factories.question.create(
        form=form,
        expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=1000), user)],
    )

    assert raise_if_question_has_any_dependencies(q2) is None

    with pytest.raises(DependencyOrderException) as e:
        raise_if_question_has_any_dependencies(q1)
    assert e.value.question == q2  # ty: ignore[unresolved-attribute]
    assert e.value.depends_on_question == q1  # ty: ignore[unresolved-attribute]


def test_update_submission_data(db_session, factories):
    question = factories.question.build()
    submission = factories.submission.build(collection=question.form.section.collection)

    assert str(question.id) not in submission.data

    data = TextSingleLine("User submitted data")
    updated_submission = update_submission_data(submission, question, data)

    assert updated_submission.data[str(question.id)] == "User submitted data"


def test_add_submission_event(db_session, factories):
    user = factories.user.build()
    submission = factories.submission.build()
    db_session.add(submission)

    add_submission_event(submission=submission, user=user, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED)

    # pull it back out of the database to also check all of the serialisation/ enums are mapped appropriately
    from_db = get_submission(submission.id, with_full_schema=True)

    assert len(from_db.events) == 1
    assert from_db.events[0].key == SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED


def test_clear_events_from_submission(db_session, factories):
    submission = factories.submission.build()
    section = factories.section.build(collection=submission.collection)
    form_one = factories.form.build(section=section)
    form_two = factories.form.build(section=section)

    add_submission_event(
        submission=submission, user=submission.created_by, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
    )
    add_submission_event(
        submission=submission, user=submission.created_by, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
    )

    # clears all keys of type
    clear_submission_events(submission=submission, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED)

    assert submission.events == []

    # clears only a specific forms
    add_submission_event(
        submission=submission,
        user=submission.created_by,
        key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED,
        form=form_one,
    )
    add_submission_event(
        submission=submission,
        user=submission.created_by,
        key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED,
        form=form_two,
    )

    clear_submission_events(submission=submission, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED, form=form_one)

    assert len(submission.events) == 1
    assert submission.events[0].form == form_two


def test_get_collection_with_full_schema(db_session, factories, track_sql_queries):
    collection = factories.collection.create()
    sections = factories.section.create_batch(3, collection=collection)
    for section in sections:
        forms = factories.form.create_batch(3, section=section)
        for form in forms:
            factories.question.create_batch(3, form=form)

    with track_sql_queries() as queries:
        from_db = get_collection(collection_id=collection.id, with_full_schema=True)
    assert from_db is not None

    # Expected queries:
    # * Initial queries for collection and user
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


def test_add_question_condition(db_session, factories):
    q0 = factories.question.create()
    question = factories.question.create(form=q0.form)
    user = factories.user.create()

    # configured by the user interface
    managed_expression = GreaterThan(minimum_value=3000, question_id=q0.id)

    add_question_condition(question, user, managed_expression)

    # check the serialisation and deserialisation is as expected
    from_db = get_question_by_id(question.id)

    assert len(from_db.expressions) == 1
    assert from_db.expressions[0].type == ExpressionType.CONDITION
    assert from_db.expressions[0].statement == f"{q0.safe_qid} > 3000"

    # check the serialised context lines up with the values in the managed expression
    assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.GREATER_THAN

    with pytest.raises(DuplicateValueError):
        add_question_condition(question, user, managed_expression)


def test_add_question_condition_blocks_on_order(db_session, factories):
    user = factories.user.create()
    q1 = factories.question.create()
    q2 = factories.question.create(form=q1.form)

    with pytest.raises(DependencyOrderException) as e:
        add_question_condition(q1, user, GreaterThan(minimum_value=1000, question_id=q2.id))
    assert str(e.value) == "Cannot add managed condition that depends on a later question"


def test_add_question_validation(db_session, factories):
    question = factories.question.create()
    user = factories.user.create()

    # configured by the user interface
    managed_expression = GreaterThan(minimum_value=3000, question_id=question.id)

    add_question_validation(question, user, managed_expression)

    # check the serialisation and deserialisation is as expected
    from_db = get_question_by_id(question.id)

    assert len(from_db.expressions) == 1
    assert from_db.expressions[0].type == ExpressionType.VALIDATION
    assert from_db.expressions[0].statement == f"{question.safe_qid} > 3000"

    # check the serialised context lines up with the values in the managed expression
    assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.GREATER_THAN


def test_update_expression(db_session, factories):
    q0 = factories.question.create()
    question = factories.question.create(form=q0.form)
    user = factories.user.create()
    managed_expression = GreaterThan(minimum_value=3000, question_id=q0.id)

    add_question_condition(question, user, managed_expression)

    updated_expression = GreaterThan(minimum_value=5000, question_id=q0.id)

    update_question_expression(question.expressions[0], updated_expression)

    assert question.expressions[0].statement == f"{q0.safe_qid} > 5000"


def test_update_expression_errors_on_validation_overlap(db_session, factories):
    question = factories.question.create()
    user = factories.user.create()
    gt_expression = GreaterThan(minimum_value=3000, question_id=question.id)

    add_question_validation(question, user, gt_expression)

    lt_expression = LessThan(maximum_value=5000, question_id=question.id)

    add_question_validation(question, user, lt_expression)
    lt_db_expression = next(db_expr for db_expr in question.expressions if db_expr.managed_name == lt_expression._key)

    with pytest.raises(DuplicateValueError):
        update_question_expression(lt_db_expression, gt_expression)


def test_remove_expression(db_session, factories):
    qid = uuid.uuid4()
    user = factories.user.create()
    question = factories.question.create(
        id=qid,
        expressions=[
            Expression.from_managed(GreaterThan(question_id=qid, minimum_value=3000), user),
        ],
    )

    assert len(question.expressions) == 1
    expression_id = question.expressions[0].id

    remove_question_expression(question, question.expressions[0])

    assert len(question.expressions) == 0

    with pytest.raises(NoResultFound, match="No row was found when one was required"):
        get_expression(expression_id)


def test_get_expression(db_session, factories):
    expression = factories.expression.create(statement="", type=ExpressionType.VALIDATION)

    db_expr = get_expression(expression.id)
    assert db_expr is expression


def test_get_expression_missing(db_session, factories):
    factories.expression.create(statement="", type=ExpressionType.VALIDATION)

    with pytest.raises(NoResultFound):
        get_expression(uuid.uuid4())
