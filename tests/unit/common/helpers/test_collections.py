import uuid

import pytest

from app.common.data.types import ExpressionType, SubmissionEventKey
from app.common.helpers.collections import SubmissionHelper
from tests.utils import AnyStringMatching


class TestSubmissionHelper:
    class TestGetOrderedVisibleForms:
        def test_ordering(self, db_session, factories):
            submission = factories.submission.build()
            _form_0 = factories.form.build(order=0, collection=submission.collection)
            _form_2 = factories.form.build(order=2, collection=submission.collection)
            _form_3 = factories.form.build(order=3, collection=submission.collection)
            _form_1 = factories.form.build(order=1, collection=submission.collection)

            helper = SubmissionHelper(submission)
            helper_forms = helper.get_ordered_visible_forms()
            assert len(helper_forms) == 4
            assert [s.order for s in helper_forms] == [0, 1, 2, 3]

    class TestGetOrderedVisibleQuestions:
        def test_ordering(self, db_session, factories):
            submission = factories.submission.build()
            form = factories.form.build(order=0, collection=submission.collection)
            _question_2 = factories.question.build(order=2, form=form)
            _question_0 = factories.question.build(order=0, form=form)
            _question_1 = factories.question.build(order=1, form=form)

            helper = SubmissionHelper(submission)
            helper_questions = helper.cached_get_ordered_visible_questions(form)
            assert len(helper_questions) == 3
            assert [s.order for s in helper_questions] == [0, 1, 2]

        def test_visible_questions_filtered(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)
            visible_question = factories.question.build(form=form)

            invisible_question = factories.question.build(form=form)
            factories.expression.build(question=invisible_question, type_=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)
            helper_questions = helper.cached_get_ordered_visible_questions(form)
            assert len(helper_questions) == 1
            assert helper_questions[0].id == visible_question.id

        def test_visible_questions_filtered_in_group(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)
            visible_question = factories.question.build(form=form)

            invisible_group = factories.group.build(form=form)
            factories.question.build(form_id=form.id, parent=invisible_group)
            factories.question.build(form_id=form.id, parent=invisible_group)
            factories.question.build(form_id=form.id, parent=invisible_group)
            factories.expression.build(question=invisible_group, type_=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)
            helper_questions = helper.cached_get_ordered_visible_questions(form)
            assert len(helper_questions) == 1
            assert helper_questions[0].id == visible_question.id

        def test_visible_questions_filtered_for_group_parent(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)
            q0 = factories.question.build(form=form)
            group = factories.group.build(form=form)
            q1 = factories.question.build(form_id=form.id, parent=group)
            q2 = factories.question.build(form_id=form.id, parent=group)
            q3 = factories.question.build(form_id=form.id, parent=group)

            factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)
            helper_questions = helper.cached_get_ordered_visible_questions(form)
            assert helper_questions == [q0, q1, q3]

            group_questions = helper.cached_get_ordered_visible_questions(group)
            assert group_questions == [q1, q3]

    class TestGetForm:
        def test_exists(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_form(form.id) == form

        def test_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                assert helper.get_form(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a form with id=[a-z0-9-]+ in collection=[a-z0-9-]+"
            )

    class TestGetQuestion:
        def test_exists(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_question(question.id) == question

        def test_does_not_exist(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                assert helper.get_question(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a question with id=[a-z0-9-]+ in collection=[a-z0-9-]+"
            )

    class TestGetFirstQuestionForForm:
        def test_at_least_one_question_in_form(self, db_session, factories):
            form = factories.form.build()

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)
            question = helper.get_first_question_for_form(form)
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000000")  # ty: ignore[possibly-unbound-attribute]

        def test_no_visible_questions_in_form(self, db_session, factories):
            form = factories.form.build()

            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_first_question_for_form(form) is None

    class TestGetLastQuestionForForm:
        def test_at_least_one_question_in_form(self, db_session, factories):
            form = factories.form.build()

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)
            question = helper.get_last_question_for_form(form)
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000004")  # ty: ignore[possibly-unbound-attribute]

        def test_no_visible_questions_in_form(self, db_session, factories):
            form = factories.form.build()

            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_last_question_for_form(form) is None

    class TestGetFormForQuestion:
        def test_question_exists_in_collection_forms(self, db_session, factories):
            collection = factories.collection.build()
            form = factories.form.build(collection=collection)

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            submission = factories.submission.build(collection=collection)

            helper = SubmissionHelper(submission)

            for question in form.cached_questions:
                assert helper.get_form_for_question(question.id) == form

        def test_question_does_not_exist_in_collection_forms(self, db_session, factories):
            form = factories.form.build()
            factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_form_for_question(uuid.UUID(int=1))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000001 "
                r"in collection=[a-z0-9-]+"
            )

    class TestGetNextQuestion:
        def test_current_question_exists_and_is_not_last_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_next_question(uuid.UUID(int=0)).id == uuid.UUID(int=1)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_next_question(uuid.UUID(int=1)).id == uuid.UUID(int=2)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_next_question(uuid.UUID(int=2)).id == uuid.UUID(int=3)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_next_question(uuid.UUID(int=3)).id == uuid.UUID(int=4)  # ty: ignore[possibly-unbound-attribute]

        def test_current_question_exists_but_is_last_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_next_question(uuid.UUID(int=4)) is None

        def test_current_question_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_next_question(uuid.UUID(int=9))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000009 "
                r"in collection=[a-z0-9-]+"
            )

        def test_next_question_ignores_not_visible_questions(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)
            question_one = factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            question_two = factories.question.build(form=form, id=uuid.UUID(int=1), order=1)
            question_three = factories.question.build(form=form, id=uuid.UUID(int=2), order=2)

            factories.expression.build(question=question_two, type_=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)

            question = helper.get_next_question(question_one.id)
            assert question
            assert question.id == question_three.id

    class TestGetPreviousQuestion:
        def test_current_question_exists_and_is_not_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_previous_question(uuid.UUID(int=1)).id == uuid.UUID(int=0)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_previous_question(uuid.UUID(int=2)).id == uuid.UUID(int=1)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_previous_question(uuid.UUID(int=3)).id == uuid.UUID(int=2)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_previous_question(uuid.UUID(int=4)).id == uuid.UUID(int=3)  # ty: ignore[possibly-unbound-attribute]

        def test_current_question_exists_but_is_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_previous_question(uuid.UUID(int=0)) is None

        def test_current_question_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_previous_question(uuid.UUID(int=9))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000009 "
                r"in collection=[a-z0-9-]+"
            )

        def test_previous_question_ignores_not_visible_questions(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)
            question_one = factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            question_two = factories.question.build(form=form, id=uuid.UUID(int=1), order=1)
            question_three = factories.question.build(form=form, id=uuid.UUID(int=2), order=2)

            factories.expression.build(question=question_two, type_=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)

            question = helper.get_previous_question(question_three.id)
            assert question
            assert question.id == question_one.id

    class TestStatuses:
        def test_all_forms_are_completed(self, db_session, factories):
            form_one = factories.form.build()
            form_two = factories.form.build(collection=form_one.collection)
            question_one = factories.question.build(form=form_one)
            question_two = factories.question.build(form=form_two)

            submission = factories.submission.build(collection=form_one.collection)
            helper = SubmissionHelper(submission)

            # empty collections are not completed
            assert helper.all_forms_are_completed is False

            submission.data[str(question_one.id)] = "User submitted data"
            helper.cached_get_answer_for_question.cache_clear()
            helper.cached_get_all_questions_are_answered_for_form.cache_clear()
            submission.events = [
                factories.submission_event.build(
                    submission=submission, form=form_one, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
                )
            ]

            # one complete form and one incomplete is still not completed
            assert helper.all_forms_are_completed is False

            submission.data[str(question_two.id)] = "User submitted data"
            helper.cached_get_answer_for_question.cache_clear()
            helper.cached_get_all_questions_are_answered_for_form.cache_clear()
            del helper.all_forms_are_completed

            # all questions complete but a form not marked as completed is still not completed
            assert helper.all_forms_are_completed is False
            del helper.all_forms_are_completed

            submission.events.append(
                factories.submission_event.build(
                    submission=submission, form=form_two, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
                )
            )

            # all questions answered and all marked as complete is complete
            assert helper.all_forms_are_completed is True

    class TestVisibleQuestion:
        def test_is_question_always_visible_with_no_conditions(self, factories):
            question = factories.question.build()
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is True

        def test_is_component_visible_not_visible_with_failing_condition(self, factories):
            question = factories.question.build()
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="False")

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is False

        def test_is_component_visible_visible_with_passing_condition(self, factories):
            question = factories.question.build()
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is True

        def test_is_component_visible_not_visible_with_nested_conditions(self, factories):
            group = factories.group.build()
            sub_group = factories.group.build(parent=group)
            question = factories.question.build(form=group.form)
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            expression = factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is True
            assert helper.is_component_visible(group, helper.cached_evaluation_context) is False

            # when nested sub-components inherit the property of their parents
            question.parent = group
            assert helper.is_component_visible(question, helper.cached_evaluation_context) is False

            # when further nested this still applies
            question.parent = sub_group
            assert helper.is_component_visible(question, helper.cached_evaluation_context) is False

            # if the parents condition changes this is reflected
            expression.statement = "True"
            assert helper.is_component_visible(question, helper.cached_evaluation_context) is True

    class TestGetCountForAddAnother:
        def test_empty(self, db_session, factories):
            group = factories.group.build()
            submission = factories.submission.build(collection=group.form.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_count_for_add_another(group) == 0

        def test_with_answers(self, db_session, factories):
            group = factories.group.build()
            question = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            submission.data[str(group.id)] = [
                {str(question.id): "answer 0"},
                {str(question.id): "answer 1"},
                {str(question.id): "answer 2"},
            ]

            helper = SubmissionHelper(submission)
            assert helper.get_count_for_add_another(group) == 3
