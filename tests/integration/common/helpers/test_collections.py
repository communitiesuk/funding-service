import uuid

import pytest

from app.common.collections.forms import build_question_form
from app.common.data.types import QuestionDataType
from app.common.helpers.collections import CollectionHelper, Integer, TextSingleLine
from tests.utils import AnyStringMatching


class TestCollectionHelper:
    class TestGetOrderedVisibleSections:
        def test_ordering(self, db_session, factories):
            collection = factories.collection.build()
            _section_2 = factories.section.build(order=2, collection_schema=collection.collection_schema)
            _section_0 = factories.section.build(order=0, collection_schema=collection.collection_schema)
            _section_1 = factories.section.build(order=1, collection_schema=collection.collection_schema)
            _section_4 = factories.section.build(order=4, collection_schema=collection.collection_schema)
            _section_3 = factories.section.build(order=3, collection_schema=collection.collection_schema)

            helper = CollectionHelper(collection)
            helper_sections = helper.get_ordered_visible_sections()
            assert len(helper_sections) == 5
            assert [s.order for s in helper_sections] == [0, 1, 2, 3, 4]

    class TestGetOrderedVisibleForms:
        def test_ordering(self, db_session, factories):
            collection = factories.collection.build()
            section = factories.section.build(collection_schema=collection.collection_schema)
            _form_0 = factories.form.build(order=0, section=section)
            _form_2 = factories.form.build(order=2, section=section)
            _form_3 = factories.form.build(order=3, section=section)
            _form_1 = factories.form.build(order=1, section=section)

            helper = CollectionHelper(collection)
            helper_forms = helper.get_ordered_visible_forms_for_section(section)
            assert len(helper_forms) == 4
            assert [s.order for s in helper_forms] == [0, 1, 2, 3]

    class TestGetOrderedVisibleQuestions:
        def test_ordering(self, db_session, factories):
            collection = factories.collection.build()
            section = factories.section.build(collection_schema=collection.collection_schema)
            form = factories.form.build(order=0, section=section)
            _question_2 = factories.question.build(order=2, form=form)
            _question_0 = factories.question.build(order=0, form=form)
            _question_1 = factories.question.build(order=1, form=form)

            helper = CollectionHelper(collection)
            helper_questions = helper.get_ordered_visible_questions_for_form(form)
            assert len(helper_questions) == 3
            assert [s.order for s in helper_questions] == [0, 1, 2]

    class TestGetSection:
        def test_exists(self, db_session, factories):
            section = factories.section.build()
            collection = factories.collection.build(collection_schema=section.collection_schema)

            helper = CollectionHelper(collection)
            assert helper.get_section(section.id) == section

        def test_does_not_exist(self, db_session, factories):
            section = factories.section.build()
            collection = factories.collection.build(collection_schema=section.collection_schema)

            helper = CollectionHelper(collection)
            with pytest.raises(ValueError) as e:
                assert helper.get_section(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a section with id=[a-z0-9-]+ in schema=[a-z0-9-]+"
            )

    class TestGetForm:
        def test_exists(self, db_session, factories):
            form = factories.form.build()
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)
            assert helper.get_form(form.id) == form

        def test_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)
            with pytest.raises(ValueError) as e:
                assert helper.get_form(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(r"Could not find a form with id=[a-z0-9-]+ in schema=[a-z0-9-]+")

    class TestGetQuestion:
        def test_exists(self, db_session, factories):
            question = factories.question.build()
            collection = factories.collection.build(collection_schema=question.form.section.collection_schema)

            helper = CollectionHelper(collection)
            assert helper.get_question(question.id) == question

        def test_does_not_exist(self, db_session, factories):
            question = factories.question.build()
            collection = factories.collection.build(collection_schema=question.form.section.collection_schema)

            helper = CollectionHelper(collection)
            with pytest.raises(ValueError) as e:
                assert helper.get_question(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a question with id=[a-z0-9-]+ in schema=[a-z0-9-]+"
            )

    class TestGetFirstQuestionForForm:
        # TODO: Extend this test suite when we add the business logic that make questions conditional

        def test_at_least_one_question_in_form(self, db_session, factories):
            form = factories.form.build()

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)
            question = helper.get_first_question_for_form(form)
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000000")

        def test_no_visible_questions_in_form(self, db_session, factories):
            form = factories.form.build()

            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)
            assert helper.get_first_question_for_form(form) is None

    class TestGetFormForQuestion:
        def test_question_exists_in_schema_forms(self, db_session, factories):
            section = factories.section.build()
            form = factories.form.build(section=section)

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            collection = factories.collection.build(collection_schema=section.collection_schema)

            helper = CollectionHelper(collection)

            for question in form.questions:
                assert helper.get_form_for_question(question.id) == form

        def test_question_does_not_exist_in_schema_forms(self, db_session, factories):
            form = factories.form.build()
            factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            with pytest.raises(ValueError) as e:
                helper.get_form_for_question(uuid.UUID(int=1))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000001 "
                r"in collection_schema=[a-z0-9-]+"
            )

    class TestGetNextQuestion:
        # TODO: Extend this test suite when we add the business logic that make questions conditional

        def test_current_question_exists_and_is_not_last_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            assert helper.get_next_question(uuid.UUID(int=0)).id == uuid.UUID(int=1)
            assert helper.get_next_question(uuid.UUID(int=1)).id == uuid.UUID(int=2)
            assert helper.get_next_question(uuid.UUID(int=2)).id == uuid.UUID(int=3)
            assert helper.get_next_question(uuid.UUID(int=3)).id == uuid.UUID(int=4)

        def test_current_question_exists_but_is_last_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            assert helper.get_next_question(uuid.UUID(int=4)) is None

        def test_current_question_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            with pytest.raises(ValueError) as e:
                helper.get_next_question(uuid.UUID(int=9))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000009 "
                r"in collection_schema=[a-z0-9-]+"
            )

    class TestGetPreviousQuestion:
        # TODO: Extend this test suite when we add the business logic that make questions conditional

        def test_current_question_exists_and_is_not_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            assert helper.get_previous_question(uuid.UUID(int=1)).id == uuid.UUID(int=0)
            assert helper.get_previous_question(uuid.UUID(int=2)).id == uuid.UUID(int=1)
            assert helper.get_previous_question(uuid.UUID(int=3)).id == uuid.UUID(int=2)
            assert helper.get_previous_question(uuid.UUID(int=4)).id == uuid.UUID(int=3)

        def test_current_question_exists_but_is_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            assert helper.get_previous_question(uuid.UUID(int=0)) is None

        def test_current_question_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            collection = factories.collection.build(collection_schema=form.section.collection_schema)

            helper = CollectionHelper(collection)

            with pytest.raises(ValueError) as e:
                helper.get_previous_question(uuid.UUID(int=9))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000009 "
                r"in collection_schema=[a-z0-9-]+"
            )

    class TestGetAndSubmitAnswerForQuestion:
        def test_submit_valid_data(self, db_session, factories):
            question = factories.question.build()
            collection = factories.collection.build(collection_schema=question.form.section.collection_schema)
            helper = CollectionHelper(collection)

            assert helper.get_answer_for_question(question.id) is None

            form = build_question_form(question)(question="User submitted data")
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == TextSingleLine("User submitted data")

        def test_get_data_maps_type(self, db_session, factories):
            question = factories.question.build(data_type=QuestionDataType.INTEGER)
            collection = factories.collection.build(collection_schema=question.form.section.collection_schema)
            helper = CollectionHelper(collection)

            form = build_question_form(question)(question=5)
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == Integer(5)
