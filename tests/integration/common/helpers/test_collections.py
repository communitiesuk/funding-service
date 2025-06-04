import pytest

from app.common.collections.forms import build_question_form
from app.common.data.types import CollectionStatusEnum, QuestionDataType
from app.common.helpers.collections import CollectionHelper, Integer, TextSingleLine
from tests.utils import AnyStringMatching


class TestCollectionHelper:
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

    class TestStatuses:
        def test_form_status_based_on_questions(self, db_session, factories):
            form = factories.form.build()
            question_one = factories.question.build(form=form)
            question_two = factories.question.build(form=form)

            collection = factories.collection.build(collection_schema=form.section.collection_schema)
            helper = CollectionHelper(collection)

            assert helper.get_status_for_form(form) == CollectionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question_one.id, build_question_form(question_one)(question="User submitted data")
            )

            assert helper.get_status_for_form(form) == CollectionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id, build_question_form(question_two)(question="User submitted data")
            )

            assert helper.get_status_for_form(form) == CollectionStatusEnum.IN_PROGRESS

            helper.toggle_form_completed(form, collection.created_by, True)

            assert helper.get_status_for_form(form) == CollectionStatusEnum.COMPLETED

        def test_form_status_with_no_questions(self, db_session, factories):
            form = factories.form.build()
            collection = factories.collection.build(collection_schema=form.section.collection_schema)
            helper = CollectionHelper(collection)
            assert helper.get_status_for_form(form) == CollectionStatusEnum.NOT_STARTED

        def test_collection_status_based_on_forms(self, db_session, factories):
            question = factories.question.build()
            form_two = factories.form.build(section=question.form.section)
            question_two = factories.question.build(form=form_two)

            collection = factories.collection.build(collection_schema=question.form.section.collection_schema)
            helper = CollectionHelper(collection)

            assert helper.status == CollectionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )
            helper.toggle_form_completed(question.form, collection.created_by, True)

            assert helper.get_status_for_form(question.form) == CollectionStatusEnum.COMPLETED
            assert helper.status == CollectionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id, build_question_form(question_two)(question="User submitted data")
            )
            helper.toggle_form_completed(question_two.form, collection.created_by, True)

            assert helper.get_status_for_form(question_two.form) == CollectionStatusEnum.COMPLETED
            assert helper.status == CollectionStatusEnum.COMPLETED

        def test_toggle_form_status(self, db_session, factories):
            question = factories.question.build()
            form = question.form
            collection = factories.collection.build(collection_schema=form.section.collection_schema)
            helper = CollectionHelper(collection)

            with pytest.raises(ValueError) as e:
                helper.toggle_form_completed(form, collection.created_by, True)

            assert str(e.value) == AnyStringMatching(
                r"Could not mark form id=[a-z0-9-]+ as complete because not all questions have been answered."
            )

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )
            helper.toggle_form_completed(form, collection.created_by, True)

            assert helper.get_status_for_form(form) == CollectionStatusEnum.COMPLETED

        def test_toggle_form_status_doesnt_change_status_if_already_completed(self, db_session, factories):
            section = factories.section.build()
            form = factories.form.build(section=section)

            # a second form with questions ensures nothing is conflating the collection and individual form statuses
            second_form = factories.form.build(section=section)

            question = factories.question.build(form=form)
            factories.question.build(form=second_form)

            collection = factories.collection.build(collection_schema=section.collection_schema)
            helper = CollectionHelper(collection)

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )
            helper.toggle_form_completed(question.form, collection.created_by, True)

            assert helper.get_status_for_form(question.form) == CollectionStatusEnum.COMPLETED

            helper.toggle_form_completed(question.form, collection.created_by, True)
            assert helper.get_status_for_form(question.form) == CollectionStatusEnum.COMPLETED
            assert len(collection.collection_metadata) == 1
