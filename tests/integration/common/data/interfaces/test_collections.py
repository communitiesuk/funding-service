import uuid

import pytest
from sqlalchemy.exc import IntegrityError, NoResultFound

from app.common.collections.types import TextSingleLineAnswer
from app.common.data.interfaces import collections
from app.common.data.interfaces.collections import (
    AddAnotherDependencyException,
    AddAnotherNotValidException,
    DataSourceItemReferenceDependencyException,
    DependencyOrderException,
    GroupContainsAddAnotherException,
    IncompatibleDataTypeException,
    NestedGroupDisplayTypeSamePageException,
    NestedGroupException,
    _validate_and_sync_component_references,
    _validate_and_sync_expression_references,
    add_component_condition,
    add_question_validation,
    add_submission_event,
    clear_submission_events,
    create_collection,
    create_form,
    create_group,
    create_question,
    delete_collection,
    delete_collection_test_submissions_created_by_user,
    delete_form,
    delete_question,
    get_collection,
    get_expression,
    get_expression_by_id,
    get_form_by_id,
    get_group_by_id,
    get_question_by_id,
    get_referenced_data_source_items_by_managed_expression,
    get_submission,
    group_name_exists,
    is_component_dependency_order_valid,
    move_component_down,
    move_component_up,
    move_form_down,
    move_form_up,
    raise_if_data_source_item_reference_dependency,
    raise_if_group_questions_depend_on_each_other,
    raise_if_nested_group_creation_not_valid_here,
    raise_if_question_has_any_dependencies,
    remove_add_another_answers_at_index,
    remove_question_expression,
    update_group,
    update_question,
    update_question_expression,
    update_submission_data,
)
from app.common.data.interfaces.exceptions import (
    DuplicateValueError,
    InvalidReferenceInExpression,
)
from app.common.data.models import (
    Collection,
    ComponentReference,
    DataSourceItem,
    Expression,
    Form,
    Group,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.types import (
    CollectionType,
    ExpressionType,
    ManagedExpressionsEnum,
    MultilineTextInputRows,
    NumberInputWidths,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventKey,
    SubmissionModeEnum,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import AnyOf, Between, GreaterThan, LessThan, Specifically


class TestGetCollection:
    def test_get_collection(self, db_session, factories):
        collection = factories.collection.create()
        from_db = get_collection(collection_id=collection.id)
        assert from_db is not None

    def test_get_collection_version(self, db_session, factories):
        collection = factories.collection.create()
        _ = factories.collection.create(id=collection.id, version=2)

        from_db = get_collection(collection_id=collection.id, version=1)
        from_db_v2 = get_collection(collection_id=collection.id, version=2)
        assert from_db.version == 1
        assert from_db_v2.version == 2

    def test_get_collection_version_latest_by_default(self, db_session, factories):
        collection = factories.collection.create()
        _ = factories.collection.create(id=collection.id, version=2)
        _ = factories.collection.create(id=collection.id, version=3)
        _ = factories.collection.create(id=collection.id, version=4)

        from_db = get_collection(collection_id=collection.id)
        assert from_db.version == 4

    def test_get_collection_with_grant_id(self, db_session, factories):
        collection = factories.collection.create()

        assert get_collection(collection_id=collection.id, grant_id=collection.grant_id) is not None

        with pytest.raises(NoResultFound):
            get_collection(collection_id=collection.id, grant_id=uuid.uuid4())

    def test_get_collection_with_type(self, db_session, factories):
        collection = factories.collection.create()

        assert get_collection(collection_id=collection.id, type_=CollectionType.MONITORING_REPORT) is collection

        # TODO: Extend with a test on another collection type when we extend the CollectionType enum.


class TestCreateCollection:
    def test_create_collection(self, db_session, factories):
        g = factories.grant.create()
        u = factories.user.create()
        collection = create_collection(name="test collection", user=u, grant=g, type_=CollectionType.MONITORING_REPORT)
        assert collection is not None
        assert collection.id is not None
        assert collection.slug == "test-collection"

        from_db = db_session.get(Collection, [collection.id, collection.version])
        assert from_db is not None

    def test_create_collection_name_is_unique_per_grant(self, db_session, factories):
        grants = factories.grant.create_batch(2)
        u = factories.user.create()

        # Check collection created initially
        create_collection(name="test_collection", user=u, grant=grants[0], type_=CollectionType.MONITORING_REPORT)

        # Check same name in a different grant is allowed
        collection_same_name_different_grant = create_collection(
            name="test_collection", user=u, grant=grants[1], type_=CollectionType.MONITORING_REPORT
        )
        assert collection_same_name_different_grant.id is not None

        # Check same name in the same grant is allowed with a different version
        collection_same_name_different_version = create_collection(
            name="test_collection", user=u, grant=grants[0], version=2, type_=CollectionType.MONITORING_REPORT
        )
        assert collection_same_name_different_version.id is not None

        # Check same name in the same grant is not allowed with the same version
        with pytest.raises(DuplicateValueError):
            create_collection(name="test_collection", user=u, grant=grants[0], type_=CollectionType.MONITORING_REPORT)


def test_get_submission(db_session, factories):
    submission = factories.submission.create()
    from_db = get_submission(submission_id=submission.id)
    assert from_db is not None


def test_get_submission_with_full_schema(db_session, factories, track_sql_queries):
    submission = factories.submission.create()
    submission_id = submission.id
    forms = factories.form.create_batch(3, collection=submission.collection)
    for form in forms:
        factories.question.create_batch(3, form=form)

    with track_sql_queries() as queries:
        from_db = get_submission(submission_id=submission_id, with_full_schema=True)
    assert from_db is not None

    # Expected queries:
    # * Load the collection with the nested relationships attached
    # * Load the forms
    # * Load the questions (components)
    # * Load any recursive questions (components)
    assert len(queries) == 4

    # Iterate over all the related models; check that no further SQL queries are emitted. The count is just a noop.
    count = 0
    with track_sql_queries() as queries:
        for f in from_db.collection.forms:
            for q in f._all_components:
                for _e in q.expressions:
                    count += 1

    assert queries == []


class TestGetFormById:
    def test_get_form(self, db_session, factories, track_sql_queries):
        form = factories.form.create()

        # fetching the form directly
        from_db = get_form_by_id(form_id=form.id)
        assert from_db.id == form.id

    def test_get_form_with_all_questions(self, db_session, factories, track_sql_queries):
        form = factories.form.create()
        question_one = factories.question.create(form=form)
        question_two = factories.question.create(form=form)
        factories.expression.create_batch(5, question=question_one, type_=ExpressionType.CONDITION, statement="")
        factories.expression.create_batch(5, question=question_two, type_=ExpressionType.CONDITION, statement="")

        # fetching the form and eagerly loading all questions and their expressions
        from_db = get_form_by_id(form_id=form.id, with_all_questions=True)

        # check we're not sending off more round trips to the database when interacting with the ORM
        count = 0
        with track_sql_queries() as queries:
            for q in from_db.cached_questions:
                for _e in q.expressions:
                    count += 1

        assert count == 10 and queries == []

    def test_get_form_with_grant(self, db_session, factories, track_sql_queries):
        form = factories.form.create()

        from_db = get_form_by_id(form_id=form.id, grant_id=form.collection.grant_id)

        with track_sql_queries() as queries:
            # access the grant; should be no more queries as eagerly loaded
            _ = from_db.collection.grant

        assert len(queries) == 0


def test_create_form(db_session, factories):
    collection = factories.collection.create()
    form = create_form(title="Test Form", collection=collection)
    assert form is not None
    assert form.id is not None
    assert form.title == "Test Form"
    assert form.order == 0
    assert form.slug == "test-form"


def test_form_name_unique_in_collection(db_session, factories):
    collection = factories.collection.create()
    form = create_form(title="test form", collection=collection)
    assert form

    with pytest.raises(DuplicateValueError):
        create_form(title="test form", collection=collection)


def test_move_form_up_down(db_session, factories):
    form1 = factories.form.create()
    form2 = factories.form.create(collection=form1.collection)

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


def test_get_group(db_session, factories):
    g = factories.group.create()
    from_db = get_group_by_id(group_id=g.id)
    assert from_db is not None


class TestCreateGroup:
    def test_create_group(self, db_session, factories):
        form = factories.form.create()
        group = create_group(
            form=form,
            text="Test Group",
        )

        assert group is not None
        assert form.components[0] == group

    def test_create_group_presentation_options(self, db_session, factories):
        form = factories.form.create()
        group = create_group(
            form=form,
            text="Test Group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )

        assert group is not None
        assert form.components[0] == group
        assert group.presentation_options.show_questions_on_the_same_page is True

    def test_create_nested_components(self, db_session, factories, track_sql_queries, app, monkeypatch):
        form = factories.form.create()

        group = create_group(
            form=form,
            text="Test Group",
        )

        create_question(
            form=form,
            text="Top Level Question",
            hint="Top Level Question Hint",
            name="Top Level Question Name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expression_context=ExpressionContext(),
        )

        depth = 2
        monkeypatch.setitem(app.config, "MAX_NESTED_GROUP_LEVELS", depth)

        def add_sub_group(parent, current_depth):
            # todo: separate tests to only cover one thing - the separate read from db here should be
            #       covered separately where a create_batch can be used to keep the tests fast
            for i in range(2):
                create_question(
                    form=form,
                    text=f"Sub Question {current_depth} {i}",
                    hint=f"Sub Question Hint {current_depth} {i}",
                    name=f"Sub Question Name {current_depth} {i}",
                    data_type=QuestionDataType.TEXT_SINGLE_LINE,
                    expression_context=ExpressionContext(),
                    parent=parent,
                )
            sub_group = create_group(form=form, text=f"Sub Group {current_depth}", parent=parent)
            if current_depth < depth:
                add_sub_group(sub_group, current_depth + 1)

        add_sub_group(group, 1)

        assert group is not None

        with track_sql_queries() as queries:
            from_db = get_form_by_id(form_id=form.id, with_all_questions=True)

        # we can get information on all the expressions and questions in the form with
        # no subsequent queries (at any level of nesting)
        qids = []
        eids = []
        with track_sql_queries() as queries:

            def iterate_components(components):
                for component in components:
                    for expression in component.expressions:
                        eids.append(expression.id)
                    if isinstance(component, Question):
                        qids.append(component.id)
                    elif isinstance(component, Group):
                        qids.append(component.id)
                        iterate_components(component.components)

            iterate_components(from_db.components)

        assert queries == []

        # the forms components are limited to ones with a direct relationship and no parents
        assert len(from_db.components) == 2
        assert len(from_db.cached_questions) == 5

    def test_cannot_create_nested_groups_with_show_questions_on_the_same_page(self, db_session, factories):
        form = factories.form.create()
        parent_group = create_group(
            form=form,
            text="Test group top",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )

        with pytest.raises(NestedGroupDisplayTypeSamePageException):
            create_group(
                form=form,
                text="Test group child",
                parent=parent_group,
            )

    def test_cannot_create_nested_group_with_more_than_max_levels_of_nesting(self, app, db_session, factories):
        assert app.config["MAX_NESTED_GROUP_LEVELS"] == 1, (
            "If changing the max level of nested groups, ensure you add tests to that level of nesting"
        )
        form = factories.form.create()
        grand_parent_group = create_group(
            form=form,
            text="Level 1",
        )
        parent_group = create_group(
            form=form,
            text="Level 2",
            parent=grand_parent_group,
        )

        with pytest.raises(NestedGroupException):
            create_group(
                form=form,
                text="Child group Level 3",
                parent=parent_group,
            )


class TestGroupNameExists:
    def test_group_name_exists(self, db_session, factories):
        form = factories.form.create()
        form2 = factories.form.create()
        assert group_name_exists("Test group", form_id=form.id) is False
        assert group_name_exists("Test group", form_id=form2.id) is False

        factories.group.create(name="Test group", form=form)

        assert group_name_exists("Test group", form_id=form.id) is True
        assert group_name_exists("Test group", form_id=form2.id) is False


class TestUpdateGroup:
    def test_update_group(self, db_session, factories):
        group = factories.group.create(
            text="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
            add_another=False,
        )

        assert group.presentation_options.show_questions_on_the_same_page is True

        updated_group = update_group(
            group, expression_context=ExpressionContext(), name="Updated test group", add_another=True
        )

        assert updated_group.name == "Updated test group"
        assert updated_group.text == "Updated test group"
        assert updated_group.slug == "updated-test-group"
        assert updated_group.add_another is True

        updated_group = update_group(
            group,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )

        assert updated_group.presentation_options.show_questions_on_the_same_page is False

    def test_update_group_unique_overlap(self, db_session, factories):
        form = factories.form.create()
        create_group(form=form, text="Overlap group name")
        group = create_group(
            form=form,
            text="Test group",
        )

        with pytest.raises(DuplicateValueError):
            update_group(
                group,
                expression_context=ExpressionContext(),
                name="Overlap group name",
            )

    def test_update_group_with_nested_groups_cant_enable_same_page(self, db_session, factories):
        form = factories.form.create()
        parent_group = create_group(
            form=form,
            text="Test group top",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        create_group(
            form=form,
            text="Test group child",
            parent=parent_group,
        )

        with pytest.raises(NestedGroupDisplayTypeSamePageException):
            update_group(
                parent_group,
                expression_context=ExpressionContext(),
                presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
            )
        assert parent_group.presentation_options.show_questions_on_the_same_page is False

    def test_update_group_with_question_dependencies_cant_enable_same_page(self, db_session, factories):
        form = factories.form.create()
        group = create_group(
            form=form,
            text="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        user = factories.user.create()
        q1 = factories.question.create(form=form, parent=group)
        _ = factories.question.create(
            form=form,
            parent=group,
            expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=100), created_by=user)],
        )

        with pytest.raises(DependencyOrderException):
            update_group(
                group,
                expression_context=ExpressionContext(),
                presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
            )
        assert group.presentation_options.show_questions_on_the_same_page is False

    def test_update_group_with_question_dependencies_can_disable_same_page(self, db_session, factories):
        form = factories.form.create()
        group = create_group(
            form=form,
            text="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        user = factories.user.create()
        q1 = factories.question.create(form=form, parent=group)
        _ = factories.question.create(
            form=form,
            parent=group,
            expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=100), created_by=user)],
        )

        update_group(
            group,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        assert group.presentation_options.show_questions_on_the_same_page is False

    def test_update_group_with_guidance_fields(self, db_session, factories):
        form = factories.form.create()
        group = create_group(
            form=form,
            text="Test Question Name",
        )

        assert group.guidance_heading is None
        assert group.guidance_body is None
        assert group.add_another_guidance_body is None

        updated_group = update_group(
            group=group,
            expression_context=ExpressionContext(),
            guidance_heading="How to answer this question",
            guidance_body="This is detailed guidance with **markdown** formatting.",
            add_another_guidance_body="What to expect when filling in this groups answers",
        )

        assert updated_group.guidance_heading == "How to answer this question"
        assert updated_group.guidance_body == "This is detailed guidance with **markdown** formatting."
        assert updated_group.add_another_guidance_body == "What to expect when filling in this groups answers"

    def test_update_group_with_add_another_presentation_options(self, db_session, factories):
        form = factories.form.create()
        group = create_group(form=form, text="Test group name")
        q1 = factories.question.create(parent=group, form=group.form)
        q2 = factories.question.create(parent=group, form=group.form)

        assert group.presentation_options.add_another_summary_line_question_ids is None

        updated_group = update_group(
            group=group,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id, q2.id]),
        )

        assert updated_group.presentation_options.add_another_summary_line_question_ids == [q1.id, q2.id]

    def test_update_group_with_presentation_options_dont_override_existing(self, db_session, factories):
        form = factories.form.create()
        group = create_group(
            form=form,
            text="Test group name",
            presentation_options=QuestionPresentationOptions(
                add_another_summary_line_question_ids=[], show_questions_on_the_same_page=False
            ),
        )
        q1 = factories.question.create(parent=group, form=group.form)

        updated_group = update_group(
            group=group,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id]),
        )

        assert updated_group.presentation_options.show_questions_on_the_same_page is False
        assert updated_group.presentation_options.add_another_summary_line_question_ids == [q1.id]

        updated_group = update_group(
            group=group,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )

        assert updated_group.presentation_options.show_questions_on_the_same_page is True
        assert updated_group.presentation_options.add_another_summary_line_question_ids == [q1.id]

    def test_update_group_containing_add_another_cant_be_add_another(self, db_session, factories):
        group = factories.group.create(add_another=False)
        factories.question.create(form=group.form, parent=group, add_another=True)

        with pytest.raises(GroupContainsAddAnotherException):
            update_group(group, expression_context=ExpressionContext(), add_another=True)
        assert group.add_another is False

    def test_update_group_inside_add_another_cant_be_add_another(self, db_session, factories):
        group = factories.group.create(add_another=True)
        factories.question.create(form=group.form, parent=group)
        group2 = factories.group.create(add_another=False, parent=group)

        with pytest.raises(AddAnotherNotValidException):
            update_group(group2, expression_context=ExpressionContext(), add_another=True)
        assert group2.add_another is False

    def test_update_group_containing_depended_on_questions_cant_be_add_another(self, db_session, factories):
        group = factories.group.create(add_another=False)
        q1 = factories.question.create(form=group.form, parent=group)
        q2 = factories.question.create(
            form=group.form,
        )
        add_question_validation(
            question=q2,
            managed_expression=GreaterThan(question_id=q1.id, minimum_value=100),
            user=factories.user.create(),
        )

        with pytest.raises(AddAnotherDependencyException) as e:
            update_group(group, expression_context=ExpressionContext(), add_another=True)
        assert group.add_another is False
        assert e.value.component == group
        assert e.value.referenced_question == q1

    def test_synced_component_references(self, db_session, factories, mocker):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        group = create_group(
            form=form,
            text="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        add_component_condition(group, user, GreaterThan(question_id=q1.id, minimum_value=100))

        spy_validate1 = mocker.spy(collections, "_validate_and_sync_component_references")
        spy_validate2 = mocker.spy(collections, "_validate_and_sync_expression_references")

        update_group(
            group,
            expression_context=ExpressionContext(),
        )

        assert spy_validate1.call_count == 1
        assert spy_validate2.call_count == 1  # Called once for each expression


class TestCreateQuestion:
    @pytest.mark.parametrize(
        "question_type",
        [
            QuestionDataType.TEXT_SINGLE_LINE,
            QuestionDataType.EMAIL,
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
            expression_context=ExpressionContext(),
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

    def test_integer(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.INTEGER,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(prefix="£", suffix="kg", width=NumberInputWidths.HUNDREDS),
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == QuestionDataType.INTEGER
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is None
        assert question.prefix == "£"
        assert question.suffix == "kg"
        assert question.width == "govuk-input--width-3"

    def test_text_multi_line(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(rows=MultilineTextInputRows.SMALL, word_limit=500),
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == QuestionDataType.TEXT_MULTI_LINE
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is None
        assert question.rows == 3
        assert question.word_limit == 500

    def test_yes_no(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.YES_NO,
            expression_context=ExpressionContext(),
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
            expression_context=ExpressionContext(),
            items=["one", "two", "three"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
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
        assert question.presentation_options.last_data_source_item_is_distinct_from_others is True

    def test_checkboxes(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.CHECKBOXES,
            expression_context=ExpressionContext(),
            items=["one", "two", "three"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == QuestionDataType.CHECKBOXES
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is not None
        assert [item.key for item in question.data_source.items] == ["one", "two", "three"]
        assert question.presentation_options.last_data_source_item_is_distinct_from_others is True

    def test_date(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.DATE,
            expression_context=ExpressionContext(),
        )
        assert question is not None
        assert question.id is not None
        assert question.text == "Test Question"
        assert question.hint == "Test Hint"
        assert question.name == "Test Question Name"
        assert question.data_type == QuestionDataType.DATE
        assert question.order == 0
        assert question.slug == "test-question"
        assert question.data_source is None

    def test_break_if_new_question_types_added(self):
        assert len(QuestionDataType) == 9, "Add a new test above if adding a new question type"

    def test_question_requires_data_type(self, db_session, factories):
        form = factories.form.create()
        with pytest.raises(IntegrityError) as e:
            create_question(
                form=form,
                text="Test Question",
                hint="Test Hint",
                name="Test Question Name",
                data_type=None,
                expression_context=ExpressionContext(),
            )
        assert "ck_component_type_question_requires_data_type" in str(e.value)

    def test_question_associated_with_group(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form, order=0)
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expression_context=ExpressionContext(),
            parent=group,
        )
        assert question.parent == group
        assert question.order == 0

    def test_validates_component_references(self, db_session, factories, mocker):
        form = factories.form.create()
        spy_validate1 = mocker.spy(collections, "_validate_and_sync_component_references")
        spy_validate2 = mocker.spy(collections, "_validate_and_sync_expression_references")

        create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expression_context=ExpressionContext(),
        )

        assert spy_validate1.call_count == 1
        assert spy_validate2.call_count == 0  # No expressions to validate


class TestUpdateQuestion:
    @pytest.mark.parametrize(
        "question_type",
        [
            QuestionDataType.TEXT_SINGLE_LINE,
            QuestionDataType.EMAIL,
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
            expression_context=ExpressionContext(),
        )
        assert question is not None
        assert question.data_source is None

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
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

    def test_integer(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.INTEGER,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(prefix="£", suffix="kg", width=NumberInputWidths.HUNDREDS),
        )
        assert question is not None

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
            presentation_options=QuestionPresentationOptions(
                prefix="$", suffix="lbs", width=NumberInputWidths.MILLIONS
            ),
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == QuestionDataType.INTEGER
        assert updated_question.slug == "updated-question"
        assert updated_question.prefix == "$"
        assert updated_question.suffix == "lbs"
        assert updated_question.width == "govuk-input--width-5"

    def test_text_multi_line(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
            expression_context=ExpressionContext(),
            presentation_options=QuestionPresentationOptions(rows=MultilineTextInputRows.SMALL, word_limit=500),
        )
        assert question is not None

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
            presentation_options=QuestionPresentationOptions(rows=MultilineTextInputRows.LARGE, word_limit=None),
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == QuestionDataType.TEXT_MULTI_LINE
        assert updated_question.slug == "updated-question"
        assert updated_question.rows == 10
        assert updated_question.word_limit is None

    def test_yes_no(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.YES_NO,
            expression_context=ExpressionContext(),
        )
        assert question is not None

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
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
            expression_context=ExpressionContext(),
            items=["option 1", "option 2", "option 3"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=False),
        )
        assert question is not None
        assert question.data_source_items == "option 1\noption 2\noption 3"
        item_ids = [item.id for item in question.data_source.items]
        assert question.presentation_options.last_data_source_item_is_distinct_from_others is False

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
            items=["option 3", "option 4", "option-1"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == QuestionDataType.RADIOS
        assert updated_question.slug == "updated-question"

        # last data source item setting removes it from this helper property
        assert updated_question.data_source_items == "option 3\noption 4"

        # Test that data source item IDs for existing/updated items are retained; new options are created.
        assert updated_question.data_source.items[0].id == item_ids[2]
        assert updated_question.data_source.items[1].id not in item_ids
        assert updated_question.data_source.items[2].id == item_ids[0]

        # The dropped item has been deleted
        assert db_session.get(DataSourceItem, item_ids[1]) is None

        assert question.presentation_options.last_data_source_item_is_distinct_from_others is True

    def test_update_radios_question_options_errors_on_referenced_data_items(self, db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        referenced_question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.RADIOS,
            expression_context=ExpressionContext(),
            items=["option 1", "option 2", "option 3"],
        )
        assert referenced_question is not None
        assert referenced_question.data_source_items == "option 1\noption 2\noption 3"

        items = referenced_question.data_source.items
        anyof_expression = AnyOf(
            question_id=referenced_question.id, items=[{"key": items[1].key, "label": items[1].label}]
        )

        first_dependent_question = factories.question.create(form=form)
        add_component_condition(first_dependent_question, user, anyof_expression)

        second_dependent_question = factories.question.create(form=form)
        add_component_condition(second_dependent_question, user, anyof_expression)

        with pytest.raises(DataSourceItemReferenceDependencyException) as error:
            update_question(
                question=referenced_question,
                expression_context=ExpressionContext(),
                text="Updated Question",
                hint="Updated Hint",
                name="Updated Question Name",
                items=["option 3", "option 4", "option-1"],
            )
        assert referenced_question == error.value.question_being_edited
        assert len(error.value.data_source_item_dependency_map) == 2
        assert (
            first_dependent_question and second_dependent_question in error.value.data_source_item_dependency_map.keys()
        )

    def test_update_checkboxes_question_options_errors_on_referenced_data_items(self, db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        referenced_question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.CHECKBOXES,
            expression_context=ExpressionContext(),
            items=["option 1", "option 2", "option 3"],
        )
        assert referenced_question is not None
        assert referenced_question.data_source_items == "option 1\noption 2\noption 3"

        items = referenced_question.data_source.items
        specifically_expression = Specifically(
            question_id=referenced_question.id,
            item={"key": items[1].key, "label": items[1].label},
        )

        first_dependent_question = factories.question.create(form=form)
        add_component_condition(first_dependent_question, user, specifically_expression)

        second_dependent_question = factories.question.create(form=form)
        add_component_condition(second_dependent_question, user, specifically_expression)

        with pytest.raises(DataSourceItemReferenceDependencyException) as error:
            update_question(
                question=referenced_question,
                expression_context=ExpressionContext(),
                text="Updated Question",
                hint="Updated Hint",
                name="Updated Question Name",
                items=["option 3", "option 4", "option-1"],
            )
        assert referenced_question == error.value.question_being_edited
        assert len(error.value.data_source_item_dependency_map) == 2
        assert (
            first_dependent_question and second_dependent_question in error.value.data_source_item_dependency_map.keys()
        )

    def test_checkboxes(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.CHECKBOXES,
            expression_context=ExpressionContext(),
            items=["option 1", "option 2", "option 3"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=False),
        )
        assert question is not None
        assert question.data_source_items == "option 1\noption 2\noption 3"
        item_ids = [item.id for item in question.data_source.items]
        assert question.presentation_options.last_data_source_item_is_distinct_from_others is False

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
            items=["option 3", "option 4", "option-1"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == QuestionDataType.CHECKBOXES
        assert updated_question.slug == "updated-question"

        # last data source item setting removes it from this helper property
        assert updated_question.data_source_items == "option 3\noption 4"

        # Test that data source item IDs for existing/updated items are retained; new options are created.
        assert updated_question.data_source.items[0].id == item_ids[2]
        assert updated_question.data_source.items[1].id not in item_ids
        assert updated_question.data_source.items[2].id == item_ids[0]

        # The dropped item has been deleted
        assert db_session.get(DataSourceItem, item_ids[1]) is None

        assert question.presentation_options.last_data_source_item_is_distinct_from_others is True

    def test_date(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.DATE,
            expression_context=ExpressionContext(),
            items=None,
            presentation_options=QuestionPresentationOptions(),
        )
        assert question is not None
        assert question.data_source_items is None
        assert question.presentation_options is not None
        assert question.slug == "test-question"

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            text="Updated Question",
            hint="Updated Hint",
            name="Updated Question Name",
        )

        assert updated_question.text == "Updated Question"
        assert updated_question.hint == "Updated Hint"
        assert updated_question.name == "Updated Question Name"
        assert updated_question.data_type == QuestionDataType.DATE
        assert updated_question.slug == "updated-question"

    def test_break_if_new_question_types_added(self):
        assert len(QuestionDataType) == 9, "Add a new test above if adding a new question type"

    def test_update_question_with_guidance_fields(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expression_context=ExpressionContext(),
        )

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            guidance_heading="How to answer this question",
            guidance_body="This is detailed guidance with **markdown** formatting.",
        )

        assert updated_question.guidance_heading == "How to answer this question"
        assert updated_question.guidance_body == "This is detailed guidance with **markdown** formatting."

    def test_update_question_guidance_optional_parameters(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expression_context=ExpressionContext(),
        )

        question.guidance_heading = "Initial heading"
        question.guidance_body = "Initial body"

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            text="Updated Question Text",
        )

        assert updated_question.text == "Updated Question Text"
        assert updated_question.guidance_heading == "Initial heading"
        assert updated_question.guidance_body == "Initial body"

    def test_update_question_clear_guidance_fields(self, db_session, factories):
        form = factories.form.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expression_context=ExpressionContext(),
        )

        question.guidance_heading = "Initial heading"
        question.guidance_body = "Initial body"

        updated_question = update_question(
            question=question,
            expression_context=ExpressionContext(),
            guidance_heading=None,
            guidance_body=None,
        )

        assert updated_question.guidance_heading is None
        assert updated_question.guidance_body is None

    def test_validates_component_and_expression_references(self, db_session, factories, mocker):
        form = factories.form.create()
        user = factories.user.create()
        question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.INTEGER,
            expression_context=ExpressionContext(),
        )
        add_question_validation(question, user, GreaterThan(question_id=question.id, minimum_value=0, inclusive=True))

        spy_validate1 = mocker.spy(collections, "_validate_and_sync_component_references")
        spy_validate2 = mocker.spy(collections, "_validate_and_sync_expression_references")

        update_question(
            question=question,
            expression_context=ExpressionContext(),
            guidance_heading=None,
            guidance_body=None,
        )

        assert spy_validate1.call_count == 1
        assert spy_validate2.call_count == 1  # called once for each expression on the question


class TestMoveComponent:
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

        move_component_up(q2)

        assert q1.order == 1
        assert q2.order == 0
        assert q3.order == 2

        move_component_down(q1)

        assert q1.order == 2
        assert q2.order == 0
        assert q3.order == 1

    def test_move_question_with_dependencies_through_reference(db_session, factories):
        form = factories.form.create()
        q1, q2 = factories.question.create_batch(2, form=form)
        q3 = factories.question.create(form=form, text=f"Reference to (({q2.safe_qid}))")

        # q3 can't move above its dependency q2
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(q3)
        assert e.value.question == q3  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q2 can't move below q3 which depends on it
        with pytest.raises(DependencyOrderException) as e:
            move_component_down(q2)
        assert e.value.question == q3  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q1 can freely move up and down as it has no dependencies
        move_component_down(q1)
        move_component_down(q1)
        move_component_up(q1)
        move_component_up(q1)

        # q2 can move up as q3 can still depend on it
        move_component_up(q2)

    def test_move_question_with_dependencies_through_expression(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1, q2 = factories.question.create_batch(2, form=form)
        q3 = factories.question.create(
            form=form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q2.id, minimum_value=3000), user)],
        )

        # q3 can't move above its dependency q2
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(q3)
        assert e.value.question == q3  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q2 can't move below q3 which depends on it
        with pytest.raises(DependencyOrderException) as e:
            move_component_down(q2)
        assert e.value.question == q3  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q1 can freely move up and down as it has no dependencies
        move_component_down(q1)
        move_component_down(q1)
        move_component_up(q1)
        move_component_up(q1)

        # q2 can move up as q3 can still depend on it
        move_component_up(q2)

    # you can't move a group above questions that it itself depends on
    def test_move_group_with_dependencies_through_reference(db_session, factories):
        form = factories.form.create()
        q1, q2 = factories.question.create_batch(2, form=form)
        group = factories.group.create(
            form=form, guidance_heading="test", guidance_body=f"Reference to (({q2.safe_qid}))"
        )

        # group can't move above its dependency q2
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(group)
        assert e.value.question == group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q2 can't move below group which depends on it
        with pytest.raises(DependencyOrderException) as e:
            move_component_down(q2)
        assert e.value.question == group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q1 can freely move up and down as it has no dependencies
        move_component_down(q1)
        move_component_down(q1)
        move_component_up(q1)
        move_component_up(q1)

    def test_move_group_with_dependencies_through_expression(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1, q2 = factories.question.create_batch(2, form=form)
        group = factories.group.create(
            form=form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q2.id, minimum_value=3000), user)],
        )

        # group can't move above its dependency q2
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(group)
        assert e.value.question == group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q2 can't move below group which depends on it
        with pytest.raises(DependencyOrderException) as e:
            move_component_down(q2)
        assert e.value.question == group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q2  # ty: ignore[unresolved-attribute]

        # q1 can freely move up and down as it has no dependencies
        move_component_down(q1)
        move_component_down(q1)
        move_component_up(q1)
        move_component_up(q1)

    def test_move_group_with_child_dependencies(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form)
        group = factories.group.create(form=form)
        _ = factories.question.create(
            form=form,
            parent=group,
            expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=3000), user)],
        )

        # you can't move a group above a question that something in the group depends on
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(group)
        assert e.value.question == group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q1  # ty: ignore[unresolved-attribute]

        with pytest.raises(DependencyOrderException) as e:
            move_component_down(q1)
        assert e.value.question == group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q1  # ty: ignore[unresolved-attribute]

    def test_move_question_with_group_dependencies(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        group = factories.group.create(form=form)
        nested_q1 = factories.question.create(form=form, parent=group)
        q2 = factories.question.create(
            form=form,
            expressions=[Expression.from_managed(GreaterThan(question_id=nested_q1.id, minimum_value=3000), user)],
        )

        # you can't move a question above a group that it depends on a question in
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(q2)
        assert e.value.question == q2  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == group  # ty: ignore[unresolved-attribute]

        with pytest.raises(DependencyOrderException) as e:
            move_component_down(group)
        assert e.value.question == q2  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == group  # ty: ignore[unresolved-attribute]

    def test_move_group_with_group_dependencies(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        group = factories.group.create(form=form)
        nested_q1 = factories.question.create(form=form, parent=group)
        group2 = factories.group.create(form=form)
        _ = factories.question.create(
            form=form,
            parent=group2,
            expressions=[Expression.from_managed(GreaterThan(question_id=nested_q1.id, minimum_value=3000), user)],
        )

        # you can't move a group above a question in a group that it depends on
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(group2)
        assert e.value.question == group2  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == group  # ty: ignore[unresolved-attribute]

        with pytest.raises(DependencyOrderException) as e:
            move_component_down(group)
        assert e.value.question == group2  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == group  # ty: ignore[unresolved-attribute]


class TestNestedGroupDependencies:
    def test_move_nested_group_with_previous_question_dependencies(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        parent_group = factories.group.create(form=form)
        q1_in_parent_group = factories.question.create(form=form, parent=parent_group)
        child_group = factories.group.create(form=form, parent=parent_group)
        factories.question.create(
            form=form,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=q1_in_parent_group.id, minimum_value=3000), user)
            ],
            parent=child_group,
        )

        # you can't move a nested group above a question it depends on
        with pytest.raises(DependencyOrderException) as e:
            move_component_up(child_group)
        assert e.value.question == child_group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q1_in_parent_group  # ty: ignore[unresolved-attribute]

        with pytest.raises(DependencyOrderException) as e:
            move_component_down(q1_in_parent_group)
        assert e.value.question == child_group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q1_in_parent_group  # ty: ignore[unresolved-attribute]

    def test_move_question_with_dependencies_on_nested_group(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        parent_group = factories.group.create(form=form)
        child_group = factories.group.create(form=form, parent=parent_group)
        q1_in_child_group = factories.question.create(
            form=form,
            parent=child_group,
        )
        q2_in_parent_group = factories.question.create(
            form=form,
            parent=parent_group,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=q1_in_child_group.id, minimum_value=3000), user)
            ],
        )

        # you can't move a nested group below a quetsion that depends on it
        with pytest.raises(DependencyOrderException) as e:
            move_component_down(child_group)
        assert e.value.question == q2_in_parent_group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == child_group  # ty: ignore[unresolved-attribute]

        with pytest.raises(DependencyOrderException) as e:
            move_component_up(q2_in_parent_group)
        assert e.value.question == q2_in_parent_group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == child_group  # ty: ignore[unresolved-attribute]

    def test_delete_depended_on_nested_group(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        parent_group = factories.group.create(form=form)
        child_group = factories.group.create(form=form, parent=parent_group)
        q1_in_child_group = factories.question.create(
            form=form,
            parent=child_group,
        )
        q2_in_parent_group = factories.question.create(
            form=form,
            parent=parent_group,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=q1_in_child_group.id, minimum_value=3000), user)
            ],
        )
        # you can't delete a nested group that a quetsion depends on
        with pytest.raises(DependencyOrderException) as e:
            delete_question(child_group)
        assert e.value.question == q2_in_parent_group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == child_group  # ty: ignore[unresolved-attribute]

    def test_delete_question_depended_on_by_nested_group(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        parent_group = factories.group.create(form=form)
        q1_in_parent_group = factories.question.create(form=form, parent=parent_group)
        child_group = factories.group.create(form=form, parent=parent_group)
        q1_in_child_group = factories.question.create(
            form=form,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=q1_in_parent_group.id, minimum_value=3000), user)
            ],
            parent=child_group,
        )

        # You can't delete a question that is depended on by a question in a nested group
        with pytest.raises(DependencyOrderException) as e:
            delete_question(q1_in_parent_group)
        assert e.value.question == q1_in_child_group  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q1_in_parent_group  # ty: ignore[unresolved-attribute]


class TestDependencyExceptionHelpers:
    def test_raise_if_nested_group_creation_not_valid_here(db_session, factories):
        form = factories.form.create()
        parent_group = factories.group.create(form=form)
        child_group = factories.group.create(form=form, parent=parent_group)

        raise_if_nested_group_creation_not_valid_here(parent_group)
        with pytest.raises(NestedGroupException):
            raise_if_nested_group_creation_not_valid_here(child_group)

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

    def test_raise_if_group_has_any_dependencies(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        group = factories.group.create(form=form)
        nested_question = factories.question.create(parent=group, form=form)
        q2 = factories.question.create(
            form=form,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=nested_question.id, minimum_value=1000), user)
            ],
        )

        with pytest.raises(DependencyOrderException) as e:
            raise_if_question_has_any_dependencies(nested_question)

        with pytest.raises(DependencyOrderException) as e:
            raise_if_question_has_any_dependencies(group)

        assert e.value.question == q2  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == group  # ty: ignore[unresolved

    def test_raise_if_group_questions_depend_on_each_other(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        group = factories.group.create(form=form)
        q1 = factories.question.create(parent=group, form=form, data_type=QuestionDataType.INTEGER)
        q2 = factories.question.create(
            parent=group,
            form=form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=1000), user)],
        )

        with pytest.raises(DependencyOrderException) as e:
            raise_if_group_questions_depend_on_each_other(group)
        assert e.value.question == q2  # ty: ignore[unresolved-attribute]
        assert e.value.depends_on_question == q1  # ty: ignore[unresolved-attribute]

    def test_raise_if_radios_data_source_item_reference_dependency(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        referenced_question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.RADIOS,
            expression_context=ExpressionContext(),
            items=["option 1", "option 2", "option 3"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )
        items = referenced_question.data_source.items
        anyof_expression = AnyOf(
            question_id=referenced_question.id, items=[{"key": items[0].key, "label": items[0].label}]
        )

        dependent_question = factories.question.create(form=form)
        add_component_condition(dependent_question, user, anyof_expression)
        items_to_delete = [referenced_question.data_source.items[0], referenced_question.data_source.items[1]]
        with pytest.raises(DataSourceItemReferenceDependencyException) as error:
            raise_if_data_source_item_reference_dependency(referenced_question, items_to_delete)

        assert referenced_question == error.value.question_being_edited
        assert len(error.value.data_source_item_dependency_map) == 1
        assert dependent_question in error.value.data_source_item_dependency_map.keys()
        assert referenced_question.presentation_options.last_data_source_item_is_distinct_from_others is True

    def test_raise_if_checkboxes_data_source_item_reference_dependency(db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        referenced_question = create_question(
            form=form,
            text="Test Question",
            hint="Test Hint",
            name="Test Question Name",
            data_type=QuestionDataType.CHECKBOXES,
            expression_context=ExpressionContext(),
            items=["option 1", "option 2", "option 3"],
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )
        items = referenced_question.data_source.items
        specifically_expression = Specifically(
            question_id=referenced_question.id,
            item={"key": items[0].key, "label": items[0].label},
        )

        dependent_question = factories.question.create(form=form)
        add_component_condition(dependent_question, user, specifically_expression)
        items_to_delete = [referenced_question.data_source.items[0], referenced_question.data_source.items[1]]
        with pytest.raises(DataSourceItemReferenceDependencyException) as error:
            raise_if_data_source_item_reference_dependency(referenced_question, items_to_delete)

        assert referenced_question == error.value.question_being_edited
        assert len(error.value.data_source_item_dependency_map) == 1
        assert dependent_question in error.value.data_source_item_dependency_map.keys()
        assert referenced_question.presentation_options.last_data_source_item_is_distinct_from_others is True


class TestUpdateSubmissionData:
    def test_update_submission_data_single_question(db_session, factories):
        question = factories.question.create()
        submission = factories.submission.create(collection=question.form.collection)

        assert str(question.id) not in submission.data

        data = TextSingleLineAnswer("User submitted data")
        updated_submission = update_submission_data(submission, question, data)

        assert updated_submission.data[str(question.id)] == "User submitted data"

        data = TextSingleLineAnswer("User edited data")
        updated_submission = update_submission_data(submission, question, data)

        assert updated_submission.data[str(question.id)] == "User edited data"

    def test_update_submission_data_add_another_group_first_answer(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form, add_another=True)
        question1 = factories.question.create(form=form, parent=group)
        question2 = factories.question.create(form=form, parent=group)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 1")

        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        assert updated_submission.data[str(group.id)] == [{str(question1.id): "Group 1 - Question 1 - Answer 1"}]

        q2_data1 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 1")

        updated_submission = update_submission_data(submission, question2, q2_data1, 0)
        assert updated_submission.data[str(group.id)] == [
            {
                str(question1.id): "Group 1 - Question 1 - Answer 1",
                str(question2.id): "Group 1 - Question 2 - Answer 1",
            },
        ]

    def test_update_submission_data_add_another_group_edit_only_answer(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form, add_another=True)
        question1 = factories.question.create(form=form, parent=group)
        question2 = factories.question.create(form=form, parent=group)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 1")
        q2_data1 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 1")

        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        updated_submission = update_submission_data(submission, question2, q2_data1, 0)

        q1_data1_updated = TextSingleLineAnswer("Group 1 - Question 1 - Updated 1")
        q2_data1_updated = TextSingleLineAnswer("Group 1 - Question 2 - Updated 1")

        updated_submission = update_submission_data(submission, question1, q1_data1_updated, 0)
        updated_submission = update_submission_data(submission, question2, q2_data1_updated, 0)

        assert updated_submission.data[str(group.id)] == [
            {
                str(question1.id): "Group 1 - Question 1 - Updated 1",
                str(question2.id): "Group 1 - Question 2 - Updated 1",
            },
        ]

    def test_update_submission_data_add_another_group_another_answer(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form, add_another=True)
        question1 = factories.question.create(form=form, parent=group)
        question2 = factories.question.create(form=form, parent=group)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 1")
        q2_data1 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 1")

        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        updated_submission = update_submission_data(submission, question2, q2_data1, 0)

        q1_data2 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 2")
        q2_data2 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 2")

        updated_submission = update_submission_data(submission, question1, q1_data2, 1)
        updated_submission = update_submission_data(submission, question2, q2_data2, 1)
        assert updated_submission.data[str(group.id)] == [
            {
                str(question1.id): "Group 1 - Question 1 - Answer 1",
                str(question2.id): "Group 1 - Question 2 - Answer 1",
            },
            {
                str(question1.id): "Group 1 - Question 1 - Answer 2",
                str(question2.id): "Group 1 - Question 2 - Answer 2",
            },
        ]

    def test_update_submission_data_add_another_group_edit_another_answer(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form, add_another=True)
        question1 = factories.question.create(form=form, parent=group)
        question2 = factories.question.create(form=form, parent=group)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 1")
        q2_data1 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 1")

        update_submission_data(submission, question1, q1_data1, 0)
        update_submission_data(submission, question2, q2_data1, 0)

        q1_data2 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 2")
        q2_data2 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 2")

        update_submission_data(submission, question1, q1_data2, 1)
        update_submission_data(submission, question2, q2_data2, 1)

        update_submission_data(submission, question1, TextSingleLineAnswer("Group 1 - Question 1 - Updated 1"), 0)
        update_submission_data(submission, question2, TextSingleLineAnswer("Group 1 - Question 2 - Updated 1"), 0)
        update_submission_data(submission, question1, TextSingleLineAnswer("Group 1 - Question 1 - Updated 2"), 1)
        updated_submission = update_submission_data(
            submission, question2, TextSingleLineAnswer("Group 1 - Question 2 - Updated 2"), 1
        )

        assert updated_submission.data[str(group.id)] == [
            {
                str(question1.id): "Group 1 - Question 1 - Updated 1",
                str(question2.id): "Group 1 - Question 2 - Updated 1",
            },
            {
                str(question1.id): "Group 1 - Question 1 - Updated 2",
                str(question2.id): "Group 1 - Question 2 - Updated 2",
            },
        ]

    def test_update_submission_data_add_another_question_first_answer(self, db_session, factories):
        form = factories.form.create()
        question1 = factories.question.create(form=form, add_another=True)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Question 1 - Answer 1")

        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        assert updated_submission.data[str(question1.id)] == [{str(question1.id): "Question 1 - Answer 1"}]

    def test_update_submission_data_add_another_question_edit_only_answer(self, db_session, factories):
        form = factories.form.create()
        question1 = factories.question.create(form=form, add_another=True)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Question 1 - Answer 1")
        updated_submission = update_submission_data(submission, question1, q1_data1, 0)

        q1_data1 = TextSingleLineAnswer("Question 1 - Updated 1")
        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        assert updated_submission.data[str(question1.id)] == [{str(question1.id): "Question 1 - Updated 1"}]

    def test_update_submission_data_add_another_question_another_answer(self, db_session, factories):
        form = factories.form.create()
        question1 = factories.question.create(form=form, add_another=True)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Question 1 - Answer 1")
        q1_data2 = TextSingleLineAnswer("Question 1 - Answer 2")

        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        updated_submission = update_submission_data(submission, question1, q1_data2, 1)
        assert updated_submission.data[str(question1.id)] == [
            {str(question1.id): "Question 1 - Answer 1"},
            {str(question1.id): "Question 1 - Answer 2"},
        ]

    def test_update_submission_data_add_another_question_edit_another_answer(self, db_session, factories):
        form = factories.form.create()
        question1 = factories.question.create(form=form, add_another=True)
        submission = factories.submission.create(collection=form.collection)

        q1_data1 = TextSingleLineAnswer("Question 1 - Answer 1")
        q1_data2 = TextSingleLineAnswer("Question 1 - Answer 2")
        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        updated_submission = update_submission_data(submission, question1, q1_data2, 1)

        q1_data1 = TextSingleLineAnswer("Question 1 - Updated 1")
        q1_data2 = TextSingleLineAnswer("Question 1 - Updated 2")
        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        updated_submission = update_submission_data(submission, question1, q1_data2, 1)

        assert updated_submission.data[str(question1.id)] == [
            {str(question1.id): "Question 1 - Updated 1"},
            {str(question1.id): "Question 1 - Updated 2"},
        ]

    def test_update_submission_data_validates_add_another_index_when_not_in_add_another(self, db_session, factories):
        form = factories.form.create()
        question = factories.question.create(form=form)
        submission = factories.submission.create(collection=form.collection)
        data = TextSingleLineAnswer("User submitted data")
        with pytest.raises(ValueError) as error:
            update_submission_data(submission, question, data, add_another_index=1)
        assert (
            str(error.value) == "add_another_index cannot be provided for questions not within an add another container"
        )

    def test_update_submission_data_validates_add_another_index_when_in_add_another(self, db_session, factories):
        form = factories.form.create()
        question = factories.question.create(form=form, add_another=True)
        submission = factories.submission.create(collection=form.collection)
        data = TextSingleLineAnswer("User submitted data")
        with pytest.raises(ValueError) as error:
            update_submission_data(submission, question, data, add_another_index=None)
        assert str(error.value) == "add_another_index must be provided for questions within an add another container"

    def test_update_submission_data_add_another_fail_if_index_not_available(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form, add_another=True)
        question1 = factories.question.create(form=form, parent=group)
        question2 = factories.question.create(form=form, parent=group)
        submission = factories.submission.create(collection=form.collection)
        q1_data1 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 1")

        with pytest.raises(ValueError) as e:
            update_submission_data(submission, question2, q1_data1, 1)
        assert str(e.value) == "Cannot update answers at index 1 as there are only 0 existing answers"
        with pytest.raises(ValueError) as e:
            update_submission_data(submission, question2, q1_data1, -1)
        assert str(e.value) == "Cannot update answers at index -1 as there are only 0 existing answers"

        updated_submission = update_submission_data(submission, question1, q1_data1, 0)
        assert updated_submission.data[str(group.id)] == [{str(question1.id): "Group 1 - Question 1 - Answer 1"}]

        q2_data1 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 1")

        with pytest.raises(ValueError) as e:
            update_submission_data(submission, question2, q2_data1, 2)
        assert str(e.value) == "Cannot update answers at index 2 as there are only 1 existing answers"

    def test_update_submission_data_many_add_another_entries(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        submission = collection.test_submissions[0]
        form = collection.forms[0]
        add_another_group = form.cached_all_components[3]
        add_another_name_question = form.cached_questions[2]
        add_another_email_question = form.cached_questions[3]

        update_submission_data(submission, add_another_name_question, TextSingleLineAnswer("Updated 3rd name"), 2)
        update_submission_data(
            submission, add_another_email_question, TextSingleLineAnswer("Updated_4th_email@stuff.com"), 3
        )
        update_submission_data(submission, add_another_name_question, TextSingleLineAnswer("Added name 6"), 5)
        updated_submission = update_submission_data(
            submission, add_another_email_question, TextSingleLineAnswer("Added_email_6@email.com"), 5
        )

        updated_data = updated_submission.data[str(add_another_group.id)]

        # check the name and email of entries we didn't change are still the same
        for i in [0, 1, 3, 4]:
            assert updated_data[i][str(add_another_name_question.id)] == f"test name {i}"
        for i in [0, 1, 2, 4]:
            assert updated_data[i][str(add_another_email_question.id)] == f"test_user_{i}@email.com"

        # check the updates we made are present
        assert updated_data[2][str(add_another_name_question.id)] == "Updated 3rd name"
        assert updated_data[3][str(add_another_email_question.id)] == "Updated_4th_email@stuff.com"

        # check the entry we added is correct
        assert updated_data[5] == {
            str(add_another_name_question.id): "Added name 6",
            str(add_another_email_question.id): "Added_email_6@email.com",
        }


def test_add_submission_event(db_session, factories):
    user = factories.user.create()
    submission = factories.submission.create()
    db_session.add(submission)

    add_submission_event(submission=submission, user=user, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED)

    # pull it back out of the database to also check all of the serialisation/ enums are mapped appropriately
    from_db = get_submission(submission.id, with_full_schema=True)

    assert len(from_db.events) == 1
    assert from_db.events[0].key == SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED


def test_clear_events_from_submission(db_session, factories):
    submission = factories.submission.create()
    form_one = factories.form.create(collection=submission.collection)
    form_two = factories.form.create(collection=submission.collection)

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
    forms = factories.form.create_batch(3, collection=collection)
    for form in forms:
        factories.question.create_batch(3, form=form)

    with track_sql_queries() as queries:
        from_db = get_collection(collection_id=collection.id, with_full_schema=True)
    assert from_db is not None

    # Expected queries:
    # * Initial queries for collection and user
    # * Load the forms
    # * Load the question (component)
    # * Load any of the questions (components)
    assert len(queries) == 5

    # No additional queries when inspecting the ORM model
    count = 0
    with track_sql_queries() as queries:
        for f in from_db.forms:
            for _q in f.cached_questions:
                count += 1

    assert queries == []


class TestIsComponentDependencyOrderValid:
    def test_with_nested_group_order(self, db_session, factories):
        form = factories.form.create()
        question = factories.question.create(form=form)
        group = factories.group.create(form=form)
        nested_question = factories.question.create(form=form, parent=group)

        assert is_component_dependency_order_valid(nested_question, question) is True


class TestExpressions:
    def test_add_question_condition(self, db_session, factories):
        q0 = factories.question.create()
        question = factories.question.create(form=q0.form)
        user = factories.user.create()

        # configured by the user interface
        managed_expression = GreaterThan(minimum_value=3000, question_id=q0.id)

        add_component_condition(question, user, managed_expression)

        # check the serialisation and deserialisation is as expected
        from_db = get_question_by_id(question.id)

        assert len(from_db.expressions) == 1
        assert from_db.expressions[0].type_ == ExpressionType.CONDITION
        assert from_db.expressions[0].statement == f"{q0.safe_qid} > 3000"

        # check the serialised context lines up with the values in the managed expression
        assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.GREATER_THAN

        with pytest.raises(DuplicateValueError):
            add_component_condition(question, user, managed_expression)

    def test_add_condition_raises_if_same_page(self, db_session, factories):
        group = factories.group.create(
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        q0 = factories.question.create(form=group.form, parent=group, data_type=QuestionDataType.INTEGER)
        q1 = factories.question.create(form=group.form, parent=group)
        user = factories.user.create()

        managed_expression = GreaterThan(minimum_value=3000, question_id=q0.id)

        with pytest.raises(DependencyOrderException):
            add_component_condition(q1, user, managed_expression)

        # check that the ORM has been rolled back and invalidated any changes from the interface
        assert q1.expressions == []

    def test_add_radios_question_condition(self, db_session, factories):
        q0 = factories.question.create(data_type=QuestionDataType.RADIOS)
        question = factories.question.create(form=q0.form)
        items = q0.data_source.items
        user = factories.user.create()

        # configured by the user interface
        managed_expression = AnyOf(
            question_id=q0.id,
            items=[{"key": items[0].key, "label": items[0].label}, {"key": items[1].key, "label": items[1].label}],
        )

        add_component_condition(question, user, managed_expression)

        from_db = get_question_by_id(question.id)

        assert len(from_db.expressions) == 1
        assert from_db.expressions[0].type_ == ExpressionType.CONDITION
        assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.ANY_OF
        assert q0.safe_qid and items[0].key and items[1].key in from_db.expressions[0].statement

        assert len(from_db.expressions[0].component_references) == 2
        assert (
            from_db.expressions[0].component_references[0].depends_on_data_source_item_id == q0.data_source.items[0].id
        )
        assert (
            from_db.expressions[0].component_references[1].depends_on_data_source_item_id == q0.data_source.items[1].id
        )

        with pytest.raises(DuplicateValueError):
            add_component_condition(question, user, managed_expression)

    def test_add_checkboxes_question_condition(self, db_session, factories):
        q0 = factories.question.create(data_type=QuestionDataType.CHECKBOXES)
        question = factories.question.create(form=q0.form)
        items = q0.data_source.items
        user = factories.user.create()

        # configured by the user interface
        managed_expression = Specifically(question_id=q0.id, item={"key": items[0].key, "label": items[0].label})

        add_component_condition(question, user, managed_expression)

        from_db = get_question_by_id(question.id)

        assert len(from_db.expressions) == 1
        assert from_db.expressions[0].type_ == ExpressionType.CONDITION
        assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.SPECIFICALLY
        assert q0.safe_qid and items[0].key in from_db.expressions[0].statement

        assert len(from_db.expressions[0].component_references) == 1
        assert (
            from_db.expressions[0].component_references[0].depends_on_data_source_item_id == q0.data_source.items[0].id
        )

        with pytest.raises(DuplicateValueError):
            add_component_condition(question, user, managed_expression)

    def test_add_question_condition_blocks_on_order(self, db_session, factories):
        user = factories.user.create()
        q1 = factories.question.create()
        q2 = factories.question.create(form=q1.form)

        with pytest.raises(DependencyOrderException) as e:
            add_component_condition(q1, user, GreaterThan(minimum_value=1000, question_id=q2.id))
        assert str(e.value) == "Cannot add managed condition that depends on a later question"

    def test_add_question_condition_blocks_on_add_another_question(self, db_session, factories):
        user = factories.user.create()
        q1 = factories.question.create(add_another=True)
        q2 = factories.question.create(form=q1.form)

        with pytest.raises(AddAnotherDependencyException) as e:
            add_component_condition(q2, user, GreaterThan(minimum_value=1000, question_id=q1.id))
        assert str(e.value) == "Cannot add managed condition that depends on an add another question"

    def test_add_question_condition_blocks_on_add_another_question_outside_group(self, db_session, factories):
        user = factories.user.create()
        q1 = factories.question.create(add_another=True)
        g1 = factories.group.create(form=q1.form, add_another=True)
        q2 = factories.question.create(form=q1.form, parent=g1)

        with pytest.raises(AddAnotherDependencyException) as e:
            add_component_condition(q2, user, GreaterThan(minimum_value=1000, question_id=q1.id))
        assert str(e.value) == "Cannot add managed condition that depends on an add another question"

    def test_add_question_condition_succeeds_add_another_question_inside_same_group(self, db_session, factories):
        user = factories.user.create()
        q1 = factories.question.create(add_another=True)
        g1 = factories.group.create(form=q1.form, add_another=True)
        q2 = factories.question.create(form=q1.form, parent=g1)
        q3 = factories.question.create(form=q1.form, parent=g1)

        add_component_condition(q3, user, GreaterThan(minimum_value=1000, question_id=q2.id))
        assert len(q3.expressions) == 1

    def test_add_question_validation(self, db_session, factories):
        question = factories.question.create()
        user = factories.user.create()

        # configured by the user interface
        managed_expression = GreaterThan(minimum_value=3000, question_id=question.id)

        add_question_validation(question, user, managed_expression)

        # check the serialisation and deserialisation is as expected
        from_db = get_question_by_id(question.id)

        assert len(from_db.expressions) == 1
        assert from_db.expressions[0].type_ == ExpressionType.VALIDATION
        assert from_db.expressions[0].statement == f"{question.safe_qid} > 3000"

        # check the serialised context lines up with the values in the managed expression
        assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.GREATER_THAN

    def test_update_expression(self, db_session, factories):
        q0 = factories.question.create()
        question = factories.question.create(form=q0.form)
        user = factories.user.create()
        managed_expression = GreaterThan(minimum_value=3000, question_id=q0.id)

        add_component_condition(question, user, managed_expression)

        updated_expression = GreaterThan(minimum_value=5000, question_id=q0.id)

        update_question_expression(question.expressions[0], updated_expression)

        assert question.expressions[0].statement == f"{q0.safe_qid} > 5000"

    def test_update_anyof_expression(self, db_session, factories):
        q0 = factories.question.create(data_type=QuestionDataType.RADIOS)
        question = factories.question.create(form=q0.form)
        items = q0.data_source.items
        user = factories.user.create()

        managed_expression = AnyOf(
            question_id=q0.id,
            items=[{"key": items[0].key, "label": items[0].label}, {"key": items[1].key, "label": items[1].label}],
        )

        add_component_condition(question, user, managed_expression)

        updated_expression = AnyOf(question_id=q0.id, items=[{"key": items[2].key, "label": items[2].label}])

        update_question_expression(question.expressions[0], updated_expression)

        from_db = get_question_by_id(question.id)

        assert len(from_db.expressions) == 1
        assert from_db.expressions[0].type_ == ExpressionType.CONDITION
        assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.ANY_OF
        assert q0.safe_qid and items[2].key in from_db.expressions[0].statement

        assert len(from_db.expressions[0].component_references) == 1
        assert (
            from_db.expressions[0].component_references[0].depends_on_data_source_item_id == q0.data_source.items[2].id
        )

    def test_update_specifically_expression(self, db_session, factories):
        q0 = factories.question.create(data_type=QuestionDataType.CHECKBOXES)
        question = factories.question.create(form=q0.form)
        items = q0.data_source.items
        user = factories.user.create()

        managed_expression = Specifically(question_id=q0.id, item={"key": items[0].key, "label": items[0].label})

        add_component_condition(question, user, managed_expression)

        updated_expression = Specifically(
            question_id=q0.id,
            item={"key": items[1].key, "label": items[1].label},
        )

        update_question_expression(question.expressions[0], updated_expression)

        from_db = get_question_by_id(question.id)

        assert len(from_db.expressions) == 1
        assert from_db.expressions[0].type_ == ExpressionType.CONDITION
        assert from_db.expressions[0].managed_name == ManagedExpressionsEnum.SPECIFICALLY
        assert q0.safe_qid and items[1].key in from_db.expressions[0].statement

        assert len(from_db.expressions[0].component_references) == 1
        assert (
            from_db.expressions[0].component_references[0].depends_on_data_source_item_id == q0.data_source.items[1].id
        )

    def test_update_expression_errors_on_validation_overlap(self, db_session, factories):
        question = factories.question.create()
        user = factories.user.create()
        gt_expression = GreaterThan(minimum_value=3000, question_id=question.id)

        add_question_validation(question, user, gt_expression)

        lt_expression = LessThan(maximum_value=5000, question_id=question.id)

        add_question_validation(question, user, lt_expression)
        lt_db_expression = next(
            db_expr for db_expr in question.expressions if db_expr.managed_name == lt_expression._key
        )

        with pytest.raises(DuplicateValueError):
            update_question_expression(lt_db_expression, gt_expression)

    def test_remove_expression(self, db_session, factories):
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

    def test_get_expression(self, db_session, factories):
        expression = factories.expression.create(statement="", type_=ExpressionType.VALIDATION)

        db_expr = get_expression(expression.id)
        assert db_expr is expression

    def test_get_expression_missing(self, db_session, factories):
        factories.expression.create(statement="", type_=ExpressionType.VALIDATION)

        with pytest.raises(NoResultFound):
            get_expression(uuid.uuid4())

    def test_get_expression_by_id(self, db_session, factories, track_sql_queries):
        question = factories.question.create(data_type=QuestionDataType.INTEGER)
        user = factories.user.create()
        managed_expression = GreaterThan(minimum_value=100, question_id=question.id)
        add_question_validation(question, user, managed_expression)

        expression_id = question.expressions[0].id
        db_session.expunge_all()  # Clear SQLAlchemy cache to force queries to be emitted again
        with track_sql_queries() as queries:
            retrieved_expression = get_expression_by_id(expression_id)

        assert len(queries) == 1

        assert retrieved_expression.id == expression_id
        assert retrieved_expression.type_ == ExpressionType.VALIDATION
        assert retrieved_expression.managed_name == "Greater than"

        with track_sql_queries() as queries:
            assert retrieved_expression.question.form.collection.grant is not None

        assert len(queries) == 0

    def test_get_expression_by_id_missing(self, db_session, factories):
        question = factories.question.create(data_type=QuestionDataType.INTEGER)
        user = factories.user.create()
        managed_expression = GreaterThan(minimum_value=100, question_id=question.id)
        add_question_validation(question, user, managed_expression)

        with pytest.raises(NoResultFound):
            get_expression_by_id(uuid.uuid4())

    def test_get_referenced_data_source_items_by_anyof_managed_expression(self, db_session, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.RADIOS)
        items = referenced_question.data_source.items
        managed_expression = AnyOf(
            question_id=referenced_question.id,
            items=[{"key": items[0].key, "label": items[0].label}, {"key": items[1].key, "label": items[1].label}],
        )
        referenced_data_source_items = get_referenced_data_source_items_by_managed_expression(managed_expression)
        assert len(referenced_data_source_items) == 2
        assert referenced_data_source_items[0] == referenced_question.data_source.items[0]

    def test_get_referenced_data_source_items_by_specifically_managed_expression(self, db_session, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.CHECKBOXES)
        items = referenced_question.data_source.items
        managed_expression = Specifically(
            question_id=referenced_question.id, item={"key": items[0].key, "label": items[0].label}
        )
        referenced_data_source_items = get_referenced_data_source_items_by_managed_expression(managed_expression)
        assert len(referenced_data_source_items) == 1
        assert referenced_data_source_items[0] == referenced_question.data_source.items[0]


class TestDeleteCollection:
    def test_delete(self, db_session, factories):
        collection = factories.collection.create()
        assert db_session.get(Collection, (collection.id, collection.version)) is not None

        delete_collection(collection)

        assert db_session.get(Collection, (collection.id, collection.version)) is None

    def test_delete_cascades_downstream(self, db_session, factories):
        collection = factories.collection.create()
        forms = factories.form.create_batch(2, collection=collection)
        questions = []
        for form in forms:
            questions.extend(factories.question.create_batch(2, form=form))

        delete_collection(collection)

        for form in forms:
            assert db_session.get(Form, form.id) is None

        for question in questions:
            assert db_session.get(Question, question.id) is None

    def test_can_delete_with_test_submissions(self, db_session, factories):
        collection = factories.collection.create(create_completed_submissions_conditional_question__test=True)

        assert collection.test_submissions
        assert not collection.live_submissions

        delete_collection(collection)

    def test_cannot_delete_if_live_submissions(self, db_session, factories):
        collection = factories.collection.create(create_completed_submissions_conditional_question__live=True)

        assert not collection.test_submissions
        assert collection.live_submissions

        with pytest.raises(ValueError):
            delete_collection(collection)


class TestDeleteForm:
    def test_delete(self, db_session, factories):
        form1 = factories.form.create()
        question1 = factories.question.create(form=form1)
        form2 = factories.form.create(collection=form1.collection)
        question2 = factories.question.create(form=form2)

        delete_form(form1)

        assert db_session.get(Form, form1.id) is None
        assert db_session.get(Question, question1.id) is None
        assert db_session.get(Form, form2.id) is form2
        assert db_session.get(Question, question2.id) is question2

    def test_form_reordering(self, db_session, factories):
        collection = factories.collection.create()
        forms = factories.form.create_batch(5, collection=collection)

        assert [f.order for f in collection.forms] == [0, 1, 2, 3, 4]
        assert collection.forms == [forms[0], forms[1], forms[2], forms[3], forms[4]]

        delete_form(forms[2])

        assert [f.order for f in collection.forms] == [0, 1, 2, 3]
        assert collection.forms == [forms[0], forms[1], forms[3], forms[4]]


class TestDeleteQuestion:
    def test_delete(self, db_session, factories):
        form = factories.form.create()
        question1 = factories.question.create(form=form)
        question2 = factories.question.create(form=form)
        question3 = factories.question.create(form=form)

        delete_question(question2)

        assert db_session.get(Question, question1.id) is question1
        assert db_session.get(Question, question2.id) is None
        assert db_session.get(Question, question3.id) is question3

    def test_form_reordering(self, db_session, factories):
        form = factories.form.create()
        questions = factories.question.create_batch(5, form=form)

        assert [q.order for q in form.cached_questions] == [0, 1, 2, 3, 4]
        assert form.cached_questions == [questions[0], questions[1], questions[2], questions[3], questions[4]]

        delete_question(questions[2])
        del form.cached_questions

        assert [q.order for q in form.cached_questions] == [0, 1, 2, 3]
        assert form.cached_questions == [questions[0], questions[1], questions[3], questions[4]]

    def test_delete_group(self, db_session, factories):
        form = factories.form.create()
        question1 = factories.question.create(form=form, order=0)
        group = factories.group.create(form=form, order=1)
        group_questions = factories.question.create_batch(3, form=form, parent=group)
        question2 = factories.question.create(form=form, order=2)

        assert form.components == [question1, group, question2]
        assert form.cached_questions == [question1, *[q for q in group_questions], question2]

        delete_question(group)
        del form.cached_questions

        assert db_session.get(Group, group.id) is None
        assert db_session.get(Question, group_questions[0].id) is None

        assert form.components == [question1, question2]
        assert form.cached_questions == [question1, question2]

    def test_nested_question_in_group(self, db_session, factories):
        form = factories.form.create()
        group = factories.group.create(form=form)
        questions = factories.question.create_batch(5, form=form, parent=group)

        assert [c.order for c in form.components] == [0]
        assert [q.order for q in group.cached_questions] == [0, 1, 2, 3, 4]
        assert form.cached_questions == [questions[0], questions[1], questions[2], questions[3], questions[4]]

        delete_question(questions[2])
        del form.cached_questions
        del group.cached_questions

        assert [c.order for c in form.components] == [0]
        assert [q.order for q in group.cached_questions] == [0, 1, 2, 3]
        assert form.cached_questions == [questions[0], questions[1], questions[3], questions[4]]

        assert db_session.get(Question, questions[2].id) is None
        assert db_session.get(Question, questions[0].id) is not None


class TestDeleteCollectionSubmissions:
    def test_delete_test_collection_submissions_created_by_user(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=3,
            create_completed_submissions_each_question_type__live=3,
        )
        user = collection.test_submissions[0].created_by

        for submission in collection.test_submissions:
            factories.submission_event.create(submission=submission, created_by=submission.created_by)
        for submission in collection.live_submissions:
            factories.submission_event.create(submission=submission, created_by=submission.created_by)

        collection.live_submissions[0].created_by = user
        collection.live_submissions[0].events[0].created_by = user

        collection.test_submissions[1].created_by = user
        collection.test_submissions[1].events[0].created_by = user

        factories.submission_event.create(submission=collection.test_submissions[0], created_by=user)

        test_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.TEST).all()
        live_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.LIVE).all()
        users_submissions_from_db = db_session.query(Submission).where(Submission.created_by == user).all()
        submission_events_from_db = db_session.query(SubmissionEvent).all()

        assert len(test_submissions_from_db) == 3
        assert len(live_submissions_from_db) == 3
        assert len(users_submissions_from_db) == 3
        assert len(submission_events_from_db) == 7

        delete_collection_test_submissions_created_by_user(collection=collection, created_by_user=user)

        test_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.TEST).all()
        live_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.LIVE).all()
        users_submissions_from_db = db_session.query(Submission).where(Submission.created_by == user).all()
        submission_events_from_db = db_session.query(SubmissionEvent).all()

        # Check that only the specified user's two test submissions & associated SubmissionEvents for that user were
        # deleted, and no live submission was deleted
        assert len(test_submissions_from_db) == 1
        assert len(live_submissions_from_db) == 3
        assert len(users_submissions_from_db) == 1
        assert len(submission_events_from_db) == 4

        for submission in test_submissions_from_db:
            assert submission.created_by is not user


class TestValidateAndSyncExpressionReferences:
    def test_creates_component_reference_for_managed_expression(self, db_session, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        dependent_question = factories.question.create(form=referenced_question.form)

        expression = Expression.from_managed(GreaterThan(question_id=referenced_question.id, minimum_value=100), user)
        dependent_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        assert len(expression.component_references) == 0

        _validate_and_sync_expression_references(expression)

        assert len(expression.component_references) == 1
        reference = expression.component_references[0]
        assert reference.component == dependent_question
        assert reference.expression == expression
        assert reference.depends_on_component == referenced_question

    def test_raises_not_implemented_for_unmanaged_expression(self, db_session, factories):
        user = factories.user.create()
        question = factories.question.create()

        expression = Expression(
            statement="1 + 1",
            context={},
            created_by=user,
            type_=ExpressionType.CONDITION,
            managed_name=None,
        )
        question.expressions.append(expression)
        db_session.add(expression)

        with pytest.raises(NotImplementedError):
            _validate_and_sync_expression_references(expression)

    def test_replaces_existing_component_references(self, db_session, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        dependent_question = factories.question.create(form=referenced_question.form)

        managed_expression = GreaterThan(question_id=referenced_question.id, minimum_value=100)
        expression = Expression.from_managed(managed_expression, user)
        dependent_question.expressions.append(expression)
        db_session.add(expression)

        existing_reference = ComponentReference(
            depends_on_component=referenced_question, component=dependent_question, expression=expression
        )
        expression.component_references = [existing_reference]
        db_session.add(existing_reference)
        db_session.flush()

        original_reference_id = existing_reference.id

        _validate_and_sync_expression_references(expression)
        db_session.flush()

        assert len(expression.component_references) == 1
        new_reference = expression.component_references[0]
        assert new_reference.id != original_reference_id
        assert new_reference.depends_on_component == referenced_question
        assert new_reference.component == dependent_question
        assert new_reference.expression == expression

    def test_creates_references_to_data_source_items(self, db_session, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.RADIOS)
        dependent_question = factories.question.create(form=referenced_question.form)

        managed_expression = Specifically(
            question_id=referenced_question.id,
            item={
                "key": referenced_question.data_source.items[0].key,
                "label": referenced_question.data_source.items[0].label,
            },
        )
        expression = Expression.from_managed(managed_expression, user)
        dependent_question.expressions.append(expression)
        db_session.add(expression)
        assert len(expression.component_references) == 0

        _validate_and_sync_expression_references(expression)
        db_session.flush()

        assert len(expression.component_references) == 1

    def test_creates_references_to_referenced_questions(self, db_session, factories):
        user = factories.user.create()
        form = factories.form.create()
        first_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        second_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        depends_on_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=form)

        expression = Expression.from_managed(
            Between(
                question_id=depends_on_question.id,
                minimum_value=None,
                minimum_expression=f"(({first_referenced_question.safe_qid}))",
                maximum_value=None,
                maximum_expression=f"(({second_referenced_question.safe_qid}))",
            ),
            user,
        )
        target_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        assert len(expression.component_references) == 0

        if hasattr(form, "cached_all_components"):
            del form.cached_all_components

        # This shouldn't raise an IncompatibleDataTypeException as the question evaluated by the managed expression
        # matches the data types of the questions used as reference values. The target_question (the one with the
        # expression attached) is irrelevant in terms of question data type.
        _validate_and_sync_expression_references(expression)

        assert len(expression.component_references) == 3
        referenced_components = {ref.depends_on_component for ref in expression.component_references}
        assert referenced_components == {depends_on_question, first_referenced_question, second_referenced_question}

    def test_raises_dependency_order_exception(self, db_session, factories):
        user = factories.user.create()
        form = factories.form.create()
        first_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        second_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)

        expression = Expression.from_managed(
            Between(
                question_id=target_question.id,
                minimum_value=None,
                minimum_expression=f"(({first_referenced_question.safe_qid}))",
                maximum_value=None,
                maximum_expression=f"(({second_referenced_question.safe_qid}))",
            ),
            user,
        )
        target_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        assert len(expression.component_references) == 0

        if hasattr(form, "cached_all_components"):
            del form.cached_all_components

        with pytest.raises(DependencyOrderException):
            _validate_and_sync_expression_references(expression)

    def test_raises_incompatible_data_type_exception(self, db_session, factories):
        user = factories.user.create()
        form = factories.form.create()
        first_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        second_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)

        expression = Expression.from_managed(
            Between(
                question_id=target_question.id,
                minimum_value=None,
                minimum_expression=f"(({first_referenced_question.safe_qid}))",
                maximum_value=None,
                maximum_expression=f"(({second_referenced_question.safe_qid}))",
            ),
            user,
        )
        target_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        assert len(expression.component_references) == 0

        if hasattr(form, "cached_all_components"):
            del form.cached_all_components

        with pytest.raises(IncompatibleDataTypeException):
            _validate_and_sync_expression_references(expression)

    def test_raises_add_another_exception_on_question(self, db_session, factories):
        user = factories.user.create()
        form = factories.form.create()
        first_referenced_question = factories.question.create(
            form=form, data_type=QuestionDataType.INTEGER, add_another=True
        )
        second_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)

        expression = Expression.from_managed(
            Between(
                question_id=target_question.id,
                minimum_value=None,
                minimum_expression=f"(({first_referenced_question.safe_qid}))",
                maximum_value=None,
                maximum_expression=f"(({second_referenced_question.safe_qid}))",
            ),
            user,
        )
        target_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        assert len(expression.component_references) == 0

        if hasattr(form, "cached_all_components"):
            del form.cached_all_components

        with pytest.raises(AddAnotherDependencyException):
            _validate_and_sync_expression_references(expression)

    def test_raises_add_another_exception_on_different_group(self, db_session, factories):
        user = factories.user.create()
        form = factories.form.create()
        first_referenced_question = factories.question.create(
            form=form, data_type=QuestionDataType.INTEGER, add_another=True
        )
        second_referenced_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, add_another=True)

        expression = Expression.from_managed(
            Between(
                question_id=target_question.id,
                minimum_value=None,
                minimum_expression=f"(({first_referenced_question.safe_qid}))",
                maximum_value=None,
                maximum_expression=f"(({second_referenced_question.safe_qid}))",
            ),
            user,
        )
        target_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        assert len(expression.component_references) == 0

        if hasattr(form, "cached_all_components"):
            del form.cached_all_components

        with pytest.raises(AddAnotherDependencyException):
            _validate_and_sync_expression_references(expression)


class TestValidateAndSyncComponentReferences:
    def test_creates_references_for_supported_fields(self, db_session, factories):
        text_question = factories.question.create()
        hint_question = factories.question.create(form=text_question.form)
        guidance_body_question = factories.question.create(form=text_question.form)
        dependent_question = factories.question.create(
            form=text_question.form,
            text=f"Reference to (({text_question.safe_qid}))",
            hint=f"Reference to (({hint_question.safe_qid}))",
            guidance_body=f"Reference to (({guidance_body_question.safe_qid}))",
        )

        # The factories create component references automatically; this will generally be the desirable behaviour
        # for tests.
        db_session.query(ComponentReference).delete()

        initial_refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        assert len(initial_refs) == 0

        _validate_and_sync_component_references(
            dependent_question,
            ExpressionContext.build_expression_context(
                collection=dependent_question.form.collection, mode="interpolation"
            ),
        )

        refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        assert {ref.depends_on_component for ref in refs} == {text_question, hint_question, guidance_body_question}

    def test_handles_multiple_interpolations(self, db_session, factories):
        ref_question1 = factories.question.create()
        ref_question2 = factories.question.create(form=ref_question1.form)
        dependent_question = factories.question.create(
            form=ref_question1.form, text=f"Compare (({ref_question1.safe_qid})) with (({ref_question2.safe_qid}))"
        )

        _validate_and_sync_component_references(
            dependent_question,
            ExpressionContext.build_expression_context(
                collection=dependent_question.form.collection, mode="interpolation"
            ),
        )
        db_session.flush()

        refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        assert {ref.depends_on_component for ref in refs} == {ref_question1, ref_question2}

    def test_handles_expression_references(self, db_session, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        dependent_question = factories.question.create(form=referenced_question.form)

        managed_expression = GreaterThan(question_id=referenced_question.id, minimum_value=100)
        expression = Expression.from_managed(managed_expression, user)
        dependent_question.expressions.append(expression)
        db_session.add(expression)
        db_session.flush()

        _validate_and_sync_component_references(
            dependent_question,
            ExpressionContext.build_expression_context(
                collection=dependent_question.form.collection, mode="interpolation"
            ),
        )
        db_session.flush()

        refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        assert len(refs) == 1
        assert refs[0].depends_on_component == referenced_question
        assert refs[0].expression == expression

    def test_throws_error_on_referencing_later_question_in_form(self, db_session, factories):
        dependent_question = factories.question.create()
        referenced_question = factories.question.create(
            form=dependent_question.form, data_type=QuestionDataType.INTEGER
        )
        dependent_question.text = f"Reference to (({referenced_question.safe_qid}))"

        with pytest.raises(InvalidReferenceInExpression):
            _validate_and_sync_component_references(
                dependent_question,
                ExpressionContext.build_expression_context(
                    collection=dependent_question.form.collection, mode="interpolation"
                ),
            )

    def test_throws_error_on_referencing_same_question_in_form(self, db_session, factories):
        question = factories.question.create()
        question.text = f"Reference to (({question.safe_qid}))"

        with pytest.raises(InvalidReferenceInExpression):
            _validate_and_sync_component_references(
                question,
                ExpressionContext.build_expression_context(collection=question.form.collection, mode="interpolation"),
            )

    def test_throws_error_on_unknown_references(self, db_session, factories):
        dependent_question = factories.question.create()

        # Set the text with an invalid reference after creation so that ComponentReferences aren't created; they'd error
        dependent_question.text = "Reference to ((some.non.question.ref)) here"

        with pytest.raises(InvalidReferenceInExpression):
            _validate_and_sync_component_references(
                dependent_question,
                ExpressionContext.build_expression_context(
                    collection=dependent_question.form.collection, mode="interpolation"
                ),
            )

        refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        assert len(refs) == 0

    def test_raises_complex_expression_exception(self, db_session, factories):
        referenced_question = factories.question.create()
        dependent_question = factories.question.create(form=referenced_question.form, text="Initial text")

        dependent_question.text = f"Complex expression (({referenced_question.safe_qid} + 100)) not allowed"

        with pytest.raises(InvalidReferenceInExpression) as exc_info:
            _validate_and_sync_component_references(
                dependent_question,
                ExpressionContext.build_expression_context(
                    collection=dependent_question.form.collection, mode="interpolation"
                ),
            )

        assert exc_info.value.field_name == "text"
        assert exc_info.value.bad_reference == f"(({referenced_question.safe_qid} + 100))"

    def test_raises_complex_expression_for_special_characters(self, db_session, factories):
        dependent_question = factories.question.create(text="Initial text")

        # Update after creation because the factory would try to create a ComponentReference and throw an error
        dependent_question.text = "Invalid expression ((question.id & something)) here"

        with pytest.raises(InvalidReferenceInExpression) as exc_info:
            _validate_and_sync_component_references(
                dependent_question,
                ExpressionContext.build_expression_context(
                    collection=dependent_question.form.collection, mode="interpolation"
                ),
            )

        assert exc_info.value.field_name == "text"
        assert exc_info.value.bad_reference == "((question.id & something))"

    def test_removes_existing_references_before_creating_new_ones(self, db_session, factories):
        old_referenced_question = factories.question.create()
        new_referenced_question = factories.question.create(form=old_referenced_question.form)
        dependent_question = factories.question.create(
            form=old_referenced_question.form, text=f"Reference to (({old_referenced_question.safe_qid}))"
        )

        refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        old_referenced_id = refs[0].id
        assert len(refs) == 1
        assert refs[0].depends_on_component == old_referenced_question

        dependent_question.text = f"Now references (({new_referenced_question.safe_qid}))"

        _validate_and_sync_component_references(
            dependent_question,
            ExpressionContext.build_expression_context(
                collection=dependent_question.form.collection, mode="interpolation"
            ),
        )
        db_session.flush()

        # Old reference should be deleted
        old_ref = db_session.get(ComponentReference, old_referenced_id)
        assert old_ref is None

        # New one should exist
        refs = db_session.query(ComponentReference).filter_by(component=dependent_question).all()
        assert len(refs) == 1
        assert refs[0].depends_on_component == new_referenced_question

    def test_works_with_groups(self, db_session, factories):
        form = factories.form.create()
        referenced_question = factories.question.create(form=form)
        group = factories.group.create(form=form, text=f"Group referencing ((({referenced_question.safe_qid})))")

        _validate_and_sync_component_references(
            group,
            ExpressionContext.build_expression_context(
                collection=referenced_question.form.collection, mode="interpolation"
            ),
        )
        db_session.flush()

        refs = db_session.query(ComponentReference).filter_by(component=group).all()
        assert len(refs) == 1
        assert refs[0].depends_on_component == referenced_question


class TestAddAnother:
    def test_remove_add_another_answers(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__number_of_add_another_answers=5,
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        add_another_group = collection.forms[0].cached_all_components[3]
        submission = collection.test_submissions[0]
        add_another_answers = submission.data[str(add_another_group.id)]
        assert len(add_another_answers) == 5

        updated_submission = remove_add_another_answers_at_index(submission, add_another_group, 2)
        updated_add_another_answers = updated_submission.data[str(add_another_group.id)]

        # check we have the right number of answers, and what was the second to last item is now last
        assert len(updated_add_another_answers) == 4
        assert "test name 4" in list(updated_add_another_answers[-1].values())

    def test_remove_add_another_answers_first_answer(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        add_another_group = collection.forms[0].cached_all_components[3]
        submission = collection.test_submissions[0]
        add_another_answers = submission.data[str(add_another_group.id)]
        assert len(add_another_answers) == 5

        updated_submission = remove_add_another_answers_at_index(submission, add_another_group, 0)
        updated_add_another_answers = updated_submission.data[str(add_another_group.id)]

        # check we have the right number of answers, and what was the second item is now first
        assert len(updated_add_another_answers) == 4
        assert "test name 1" in list(updated_add_another_answers[0].values())

    def test_remove_add_another_answers_last_answer(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__number_of_add_another_answers=5,
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        add_another_group = collection.forms[0].cached_all_components[3]
        submission = collection.test_submissions[0]
        add_another_answers = submission.data[str(add_another_group.id)]
        assert len(add_another_answers) == 5

        updated_submission = remove_add_another_answers_at_index(submission, add_another_group, 4)
        updated_add_another_answers = updated_submission.data[str(add_another_group.id)]

        # check we have the right number of answers, and what was the second to last item is now last
        assert len(updated_add_another_answers) == 4
        assert "test name 3" in list(updated_add_another_answers[-1].values())

    def test_remove_add_another_answers_only_answer(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__number_of_add_another_answers=1,
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        add_another_group = collection.forms[0].cached_all_components[3]
        submission = collection.test_submissions[0]
        add_another_answers = submission.data[str(add_another_group.id)]
        assert len(add_another_answers) == 1

        updated_submission = remove_add_another_answers_at_index(submission, add_another_group, 0)
        updated_add_another_answers = updated_submission.data[str(add_another_group.id)]

        assert updated_add_another_answers is not None
        assert len(updated_add_another_answers) == 0

    def test_remove_add_another_answers_validates_add_another_index(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__number_of_add_another_answers=1,
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        add_another_group = collection.forms[0].cached_all_components[3]
        submission = collection.test_submissions[0]
        with pytest.raises(ValueError) as e:
            remove_add_another_answers_at_index(submission, add_another_group, 1)
        assert str(e.value) == "Cannot remove answers at index 1 as there are only 1 existing answers"
        with pytest.raises(ValueError) as e:
            remove_add_another_answers_at_index(submission, add_another_group, -1)
        assert str(e.value) == "Cannot remove answers at index -1 as there are only 1 existing answers"

    def test_remove_add_another_answers_validates_add_another_index_no_existing_answers(self, db_session, factories):
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__number_of_add_another_answers=0,
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        add_another_group = collection.forms[0].cached_all_components[3]
        submission = collection.test_submissions[0]
        with pytest.raises(ValueError) as e:
            remove_add_another_answers_at_index(submission, add_another_group, 1)
        assert str(e.value) == "Cannot remove answers at index 1 as there are only 0 existing answers"
        with pytest.raises(ValueError) as e:
            remove_add_another_answers_at_index(submission, add_another_group, -1)
        assert str(e.value) == "Cannot remove answers at index -1 as there are only 0 existing answers"
