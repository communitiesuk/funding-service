import uuid
from datetime import datetime

import pytest

from app.common.data.types import (
    ConditionsOperator,
    ExpressionType,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventType,
    SubmissionModeEnum,
)
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
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000000")

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
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000004")

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

            assert helper.get_next_question(uuid.UUID(int=0)).id == uuid.UUID(int=1)
            assert helper.get_next_question(uuid.UUID(int=1)).id == uuid.UUID(int=2)
            assert helper.get_next_question(uuid.UUID(int=2)).id == uuid.UUID(int=3)
            assert helper.get_next_question(uuid.UUID(int=3)).id == uuid.UUID(int=4)

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

        def test_next_question_with_add_another_index(self, factories):
            form = factories.form.build()
            q0 = factories.question.build(form=form, order=0)
            group = factories.group.build(form=form, add_another=True, order=1)
            q1 = factories.question.build(parent=group, data_type=QuestionDataType.INTEGER, order=0)
            q2 = factories.question.build(parent=group, order=1)
            q3 = factories.question.build(parent=group, order=2)
            q4 = factories.question.build(form=form, order=2)

            submission = factories.submission.build(collection=form.collection)
            factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} > 50")

            submission.data = {str(group.id): [{str(q1.id): {"value": 55}}, {str(q1.id): {"value": 20}}]}

            helper = SubmissionHelper(submission)

            assert helper.get_next_question(q0.id).id == q1.id
            assert helper.get_next_question(q3.id).id == q4.id

            # without any information to go with, the default behaviour is for the condition to fail closed
            # which will mean the question is skipped
            assert helper.get_next_question(q1.id).id == q3.id

            # when the context is provided, the question is shown or hidden appropriately
            assert helper.get_next_question(q1.id, add_another_index=0).id == q2.id
            assert helper.get_next_question(q1.id, add_another_index=1).id == q3.id

    class TestGetPreviousQuestion:
        def test_current_question_exists_and_is_not_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_previous_question(uuid.UUID(int=1)).id == uuid.UUID(int=0)
            assert helper.get_previous_question(uuid.UUID(int=2)).id == uuid.UUID(int=1)
            assert helper.get_previous_question(uuid.UUID(int=3)).id == uuid.UUID(int=2)
            assert helper.get_previous_question(uuid.UUID(int=4)).id == uuid.UUID(int=3)

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

        def test_previous_question_with_add_another_index(self, factories):
            form = factories.form.build()
            q0 = factories.question.build(form=form, order=0)
            group = factories.group.build(form=form, add_another=True, order=1)
            q1 = factories.question.build(parent=group, data_type=QuestionDataType.INTEGER, order=0)
            q2 = factories.question.build(parent=group, order=1)
            q3 = factories.question.build(parent=group, order=2)
            q4 = factories.question.build(form=form, order=2)

            submission = factories.submission.build(collection=form.collection)
            factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} > 50")

            submission.data = {str(group.id): [{str(q1.id): {"value": 55}}, {str(q1.id): {"value": 20}}]}

            helper = SubmissionHelper(submission)

            assert helper.get_previous_question(q1.id).id == q0.id
            assert helper.get_previous_question(q4.id).id == q3.id

            assert helper.get_previous_question(q3.id).id == q1.id

            assert helper.get_previous_question(q3.id, add_another_index=0).id == q2.id
            assert helper.get_previous_question(q3.id, add_another_index=1).id == q1.id

    class TestGetAllQuestionsAreAnsweredForForm:
        def test_all_questions_answered(self, factories):
            q1 = factories.question.build()
            q2 = factories.question.build(form=q1.form)
            submission = factories.submission.build(collection=q1.form.collection)
            submission.data = {str(q1.id): "answer 1"}
            helper = SubmissionHelper(submission)

            all_answered = helper.cached_get_all_questions_are_answered_for_form(q1.form).all_answered
            assert all_answered is False

            helper.cached_get_answer_for_question.cache_clear()
            helper.cached_get_all_questions_are_answered_for_form.cache_clear()

            submission.data = {str(q1.id): "answer 1", str(q2.id): "answer 2"}

            all_answered = helper.cached_get_all_questions_are_answered_for_form(q1.form).all_answered
            assert all_answered is True

        # this may sit more nicely as an integration test as its checking expression evaluation
        # and other moving parts
        def test_all_questions_answered_with_conditions(self, factories):
            q1 = factories.question.build()
            q2 = factories.question.build(form=q1.form)
            submission = factories.submission.build(collection=q1.form.collection)
            submission.data = {str(q1.id): "answer 1"}
            helper = SubmissionHelper(submission)

            factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="False")

            all_answered = helper.cached_get_all_questions_are_answered_for_form(q1.form).all_answered
            assert all_answered is True

        def test_all_questions_answered_with_add_another(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(form=group.form, parent=group)
            q2 = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            submission.data = {
                str(group.id): [{str(q1.id): "answer 1"}, {str(q1.id): "answer 2", str(q2.id): "answer 2"}]
            }
            helper = SubmissionHelper(submission)

            all_answered = helper.cached_get_all_questions_are_answered_for_form(group.form).all_answered
            assert all_answered is False

            helper.cached_get_answer_for_question.cache_clear()
            helper.cached_get_all_questions_are_answered_for_form.cache_clear()

            submission.data = {
                str(group.id): [
                    {str(q1.id): "answer 1", str(q2.id): "answer 1"},
                    {str(q1.id): "answer 2", str(q2.id): "answer 2"},
                ]
            }

            all_answered = helper.cached_get_all_questions_are_answered_for_form(group.form).all_answered
            assert all_answered is True

        # this may sit more nicely as an integration test as its checking expression evaluation
        # and other moving parts
        def test_all_questions_answered_with_add_another_conditions(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(form=group.form, parent=group, data_type=QuestionDataType.INTEGER)
            q2 = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            submission.data = {
                str(group.id): [
                    {str(q1.id): {"value": 20}},
                    {str(q1.id): {"value": 55}, str(q2.id): "answer 2"},
                    {str(q1.id): {"value": 60}},
                ]
            }
            factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} > 50")
            helper = SubmissionHelper(submission)

            all_answered = helper.cached_get_all_questions_are_answered_for_form(group.form).all_answered
            assert all_answered is False

            helper.cached_get_answer_for_question.cache_clear()
            helper.cached_get_all_questions_are_answered_for_form.cache_clear()

            submission.data = {
                str(group.id): [
                    {str(q1.id): {"value": 20}},
                    {str(q1.id): {"value": 55}, str(q2.id): "answer 2"},
                    {str(q1.id): {"value": 60}, str(q2.id): "answer 3"},
                ]
            }

            all_answered = helper.cached_get_all_questions_are_answered_for_form(group.form).all_answered
            assert all_answered is True

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
                    submission=submission,
                    target_key=form_one.id,
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
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
                    submission=submission,
                    target_key=form_two.id,
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
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

        def test_is_component_visible_visible_with_add_another_expression_index(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(form=group.form, parent=group)
            q2 = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            submission.data[str(group.id)] = [{str(q1.id): "True"}, {str(q1.id): "False"}]
            helper = SubmissionHelper(submission)

            factories.expression.build(
                question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} == 'True'"
            )

            assert helper.is_component_visible(q1, helper.cached_evaluation_context) is True

            # the expression defaults to false if there is an condition on the same add another container and
            # no index is provided
            assert helper.is_component_visible(q2, helper.cached_evaluation_context) is False

            # the expression is evaluated appropriately when an index is provided
            assert helper.is_component_visible(q2, helper.cached_evaluation_context, add_another_index=0) is True
            assert helper.is_component_visible(q2, helper.cached_evaluation_context, add_another_index=1) is False

        def test_is_component_visible_with_any_operator_one_true_condition(self, factories):
            question = factories.question.build(conditions_operator=ConditionsOperator.ANY)
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="False")

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is True

        def test_is_component_visible_with_any_operator_all_false_conditions(self, factories):
            question = factories.question.build(conditions_operator=ConditionsOperator.ANY)
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="False")
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="False")

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is False

        def test_is_component_visible_with_all_operator_requires_all_true(self, factories):
            question = factories.question.build(conditions_operator=ConditionsOperator.ALL)
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="False")

            assert helper.is_component_visible(question, helper.cached_evaluation_context) is False

        def test_is_component_visible_with_nested_groups_different_operators(self, factories):
            group = factories.group.build(conditions_operator=ConditionsOperator.ANY)
            question = factories.question.build(
                form=group.form, parent=group, conditions_operator=ConditionsOperator.ALL
            )
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            # Group has ANY operator with one True and one False condition
            factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

            # Question has ALL operator with all True conditions
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")

            assert helper.is_component_visible(group, helper.cached_evaluation_context) is True
            assert helper.is_component_visible(question, helper.cached_evaluation_context) is True

        def test_is_component_visible_child_hidden_when_parent_hidden_regardless_of_operator(self, factories):
            group = factories.group.build(conditions_operator=ConditionsOperator.ALL)
            question = factories.question.build(
                form=group.form, parent=group, conditions_operator=ConditionsOperator.ANY
            )
            helper = SubmissionHelper(factories.submission.build(collection=question.form.collection))

            # Group has ALL operator with one False condition (so hidden)
            factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

            # Question has ANY operator with one True condition
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")

            assert helper.is_component_visible(group, helper.cached_evaluation_context) is False
            assert helper.is_component_visible(question, helper.cached_evaluation_context) is False

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

    class TestGetAnswerSummaryForAddAnother:
        def test_valid_summary_line_no_option_gets_all(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(parent=group)
            q2 = factories.question.build(parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            submission.data[str(group.id)] = [
                {str(q1.id): "line 0 answer 0", str(q2.id): "line 0 answer 1"},
                {str(q1.id): "line 1 answer 0", str(q2.id): "line 1 answer 1"},
                {str(q1.id): "line 2 answer 0", str(q2.id): "line 2 answer 1"},
            ]
            helper = SubmissionHelper(submission)
            assert (
                helper.get_answer_summary_for_add_another(group, add_another_index=0).summary
                == "line 0 answer 0, line 0 answer 1"
            )

        def test_valid_summary_line_no_valid_options_gets_all(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(parent=group)
            q2 = factories.question.build(parent=group)

            group.question_presentation_options = QuestionPresentationOptions(
                add_another_summary_line_question_ids=[uuid.uuid4(), uuid.uuid4()]
            )
            submission = factories.submission.build(collection=group.form.collection)
            submission.data[str(group.id)] = [
                {str(q1.id): "line 0 answer 0", str(q2.id): "line 0 answer 1"},
                {str(q1.id): "line 1 answer 0", str(q2.id): "line 1 answer 1"},
                {str(q1.id): "line 2 answer 0", str(q2.id): "line 2 answer 1"},
            ]
            helper = SubmissionHelper(submission)
            assert (
                helper.get_answer_summary_for_add_another(group, add_another_index=0).summary
                == "line 0 answer 0, line 0 answer 1"
            )

        def test_valid_summary_line_valid_options_subselect_questions(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(parent=group)
            q2 = factories.question.build(parent=group)

            group.presentation_options = QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id])
            submission = factories.submission.build(collection=group.form.collection)
            submission.data[str(group.id)] = [
                {str(q1.id): "line 0 answer 0", str(q2.id): "line 0 answer 1"},
                {str(q1.id): "line 1 answer 0", str(q2.id): "line 1 answer 1"},
                {str(q1.id): "line 2 answer 0", str(q2.id): "line 2 answer 1"},
            ]
            helper = SubmissionHelper(submission)
            assert helper.get_answer_summary_for_add_another(group, add_another_index=0).summary == "line 0 answer 0"

        def test_empty_for_no_answers(self, factories):
            group = factories.group.build(add_another=True)
            factories.question.build(parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            helper = SubmissionHelper(submission)
            submission.data = {str(group.id): [{}]}

            assert helper.get_answer_summary_for_add_another(group, add_another_index=0).summary == ""

        def test_valid_summary_line_for_single_add_another_question(self, factories):
            q1 = factories.question.build(add_another=True)
            submission = factories.submission.build(collection=q1.form.collection)
            submission.data = {str(q1.id): [{str(q1.id): "line 0 answer 0"}]}
            helper = SubmissionHelper(submission)
            assert helper.get_answer_summary_for_add_another(q1, add_another_index=0).summary == "line 0 answer 0"

        def test_raises_for_non_add_another(self, factories):
            q1 = factories.question.build(add_another=False)
            submission = factories.submission.build(collection=q1.form.collection)
            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_answer_summary_for_add_another(q1, add_another_index=0)
            assert str(e.value) == "answer summaries can only be generated for components in an add another container"

        def test_get_all_answered(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(form=group.form, parent=group)
            q2 = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(collection=group.form.collection)
            submission.data[str(group.id)] = [
                {str(q1.id): "True"},
                {str(q1.id): "False"},
                {str(q1.id): "True", str(q2.id): "True"},
            ]
            helper = SubmissionHelper(submission)

            factories.expression.build(
                question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} == 'True'"
            )

            assert helper.get_answer_summary_for_add_another(q1, add_another_index=0).is_answered is False
            assert helper.get_answer_summary_for_add_another(q1, add_another_index=1).is_answered is True
            assert helper.get_answer_summary_for_add_another(q1, add_another_index=1).is_answered is True

    class TestOrderedEvents:
        def test_ordered_events(self, factories):
            submission = factories.submission.build(mode=SubmissionModeEnum.LIVE)
            event_1 = factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                created_at_utc=datetime(2020, 1, 1, 13, 30, 0),
            )
            event_2 = factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                created_at_utc=datetime(2025, 12, 1, 13, 30, 0),
            )
            event_3 = factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                created_at_utc=datetime(2022, 6, 1, 13, 30, 0),
            )

            helper = SubmissionHelper(submission)

            assert helper.ordered_events == [event_2, event_3, event_1]

    class TestSentForCertificationBy:
        def test_property_gets_submitted_by_user(self, factories):
            user = factories.user.build()
            submission = factories.submission.build(mode=SubmissionModeEnum.LIVE)
            factories.submission_event.build(
                submission=submission, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION, created_by=user
            )
            helper = SubmissionHelper(submission)

            assert helper.sent_for_certification_by == user

        def test_property_returns_none_when_no_submission_for_certification(self, factories):
            submission = factories.submission.build(mode=SubmissionModeEnum.LIVE)
            helper = SubmissionHelper(submission)

            assert helper.sent_for_certification_by is None

        def test_property_with_multiple_submission_events(self, factories):
            user = factories.user.build()
            user2 = factories.user.build()
            submission = factories.submission.build(mode=SubmissionModeEnum.LIVE)
            factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                created_by=user2,
                created_at_utc=datetime(2020, 1, 1, 13, 30, 0),
            )
            factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                created_by=user,
                created_at_utc=datetime(2025, 12, 1, 13, 30, 0),
            )
            factories.submission_event.build(
                submission=submission,
                event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                created_by=user2,
                created_at_utc=datetime(2022, 6, 1, 13, 30, 0),
            )
            helper = SubmissionHelper(submission)

            assert helper.sent_for_certification_by == user
