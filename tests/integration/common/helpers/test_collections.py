import csv
import json
import uuid
from datetime import date, datetime
from io import StringIO
from unittest import mock

import pytest

from app.common.collections.forms import build_question_form
from app.common.collections.types import (
    NOT_ASKED,
    DateAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    YesNoAnswer,
)
from app.common.data import interfaces
from app.common.data.types import QuestionDataType, SubmissionModeEnum, SubmissionStatusEnum, TasklistTaskStatusEnum
from app.common.expressions import ExpressionContext
from app.common.filters import format_datetime
from app.common.helpers.collections import (
    CollectionHelper,
    SubmissionHelper,
    _deserialise_question_type,
)
from tests.utils import AnyStringMatching

EC = ExpressionContext


class TestSubmissionHelper:
    class TestGetAndSubmitAnswerForQuestion:
        def test_submit_valid_data(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.cached_get_answer_for_question(question.id) is None

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="User submitted data"
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("User submitted data")

        def test_get_data_maps_type(self, db_session, factories):
            question = factories.question.build(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.INTEGER
            )
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294=5
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.cached_get_answer_for_question(question.id) == IntegerAnswer(value=5)

        def test_can_get_falsey_answers(self, db_session, factories):
            question = factories.question.build(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.INTEGER
            )
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294=0
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.cached_get_answer_for_question(question.id) == IntegerAnswer(value=0)

        def test_cannot_submit_answer_on_submitted_submission(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="User submitted data"
            )
            helper.submit_answer_for_question(question.id, form)
            helper.toggle_form_completed(question.form, submission.created_by, True)
            helper.submit(submission.created_by)

            with pytest.raises(ValueError) as e:
                helper.submit_answer_for_question(question.id, form)

            assert str(e.value) == AnyStringMatching(
                "Could not submit answer for question_id=[a-z0-9-]+ "
                "because submission id=[a-z0-9-]+ is already submitted."
            )

    class TestFormData:
        def test_no_submission_data(self, factories):
            form = factories.form.build()
            form_two = factories.form.build(collection=form.collection)
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            factories.question.build(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"))

            submission = factories.submission.build(collection=form.collection)
            helper = SubmissionHelper(submission)

            assert helper.cached_form_data == {}

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 9, "Update this test if adding new questions"

            form = factories.form.build()
            form_two = factories.form.build(collection=form.collection)
            q1 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            )
            q2 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"),
                data_type=QuestionDataType.TEXT_MULTI_LINE,
            )
            q3 = factories.question.build(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"), data_type=QuestionDataType.INTEGER
            )
            q4 = factories.question.build(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994297"), data_type=QuestionDataType.YES_NO
            )
            q5 = factories.question.build(
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994298"),
                data_type=QuestionDataType.RADIOS,
                data_source__items__key="my-key",
                data_source__items__label="My label",
            )
            q6 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994299"),
                data_type=QuestionDataType.EMAIL,
            )
            q7 = factories.question.build(
                form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429a"), data_type=QuestionDataType.URL
            )
            q8 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429b"),
                data_type=QuestionDataType.CHECKBOXES,
                data_source__items=[],
            )
            q8.data_source.items = [
                factories.data_source_item.build(data_source=q8.data_source, key=key, label=label)
                for key, label in [("cheddar", "Cheddar"), ("brie", "Brie"), ("stilton", "Stilton")]
            ]
            q9 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429c"),
                data_type=QuestionDataType.DATE,
            )

            submission = factories.submission.build(
                collection=form.collection,
                data={
                    str(q1.id): TextSingleLineAnswer("answer").get_value_for_submission(),
                    str(q2.id): TextMultiLineAnswer("answer\nthis").get_value_for_submission(),
                    str(q3.id): IntegerAnswer(value=50).get_value_for_submission(),
                    str(q4.id): YesNoAnswer(True).get_value_for_submission(),  # ty: ignore[missing-argument]
                    str(q5.id): SingleChoiceFromListAnswer(key="my-key", label="My label").get_value_for_submission(),
                    str(q6.id): TextSingleLineAnswer("name@example.com").get_value_for_submission(),
                    str(q7.id): TextSingleLineAnswer("https://example.com").get_value_for_submission(),
                    str(q8.id): MultipleChoiceFromListAnswer(
                        choices=[{"key": "cheddar", "label": "Cheddar"}, {"key": "stilton", "label": "Stilton"}]
                    ).get_value_for_submission(),
                    str(q9.id): DateAnswer(answer=date(2003, 2, 1)).get_value_for_submission(),
                },
            )
            helper = SubmissionHelper(submission)

            assert helper.cached_form_data == {
                "q_d696aebc49d24170a92fb6ef42994294": "answer",
                "q_d696aebc49d24170a92fb6ef42994295": "answer\nthis",
                "q_d696aebc49d24170a92fb6ef42994296": 50,
                "q_d696aebc49d24170a92fb6ef42994297": True,
                "q_d696aebc49d24170a92fb6ef42994298": "my-key",
                "q_d696aebc49d24170a92fb6ef42994299": "name@example.com",
                "q_d696aebc49d24170a92fb6ef4299429a": "https://example.com",
                "q_d696aebc49d24170a92fb6ef4299429b": ["cheddar", "stilton"],
                "q_d696aebc49d24170a92fb6ef4299429c": date(2003, 2, 1),
            }

        def test_with_add_another_groups(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=2,
            )
            questions = collection.forms[0].cached_questions
            helper = SubmissionHelper(collection.test_submissions[0])

            assert helper.cached_form_data == {
                f"{questions[0].safe_qid}": "test name",
                f"{questions[1].safe_qid}": "test org name",
                f"{questions[2].safe_qid}": ["test name 0", "test name 1"],
                f"{questions[3].safe_qid}": ["test_user_0@email.com", "test_user_1@email.com"],
                f"{questions[4].safe_qid}": 3,
            }

    class TestExpressionContext:
        def test_no_submission_data(self, factories):
            form = factories.form.build()
            form_two = factories.form.build(collection=form.collection)
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            factories.question.build(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"))

            submission = factories.submission.build(collection=form.collection)
            helper = SubmissionHelper(submission)

            assert helper.cached_evaluation_context == ExpressionContext()

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 9, "Update this test if adding new questions"

            form = factories.form.build()
            form_two = factories.form.build(collection=form.collection)
            q1 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            )
            q2 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"),
                data_type=QuestionDataType.TEXT_MULTI_LINE,
            )
            q3 = factories.question.build(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"), data_type=QuestionDataType.INTEGER
            )
            q4 = factories.question.build(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994297"), data_type=QuestionDataType.YES_NO
            )
            q5 = factories.question.build(
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994298"),
                data_type=QuestionDataType.RADIOS,
                data_source__items__key="my-key",
                data_source__items__label="My label",
            )
            q6 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994299"),
                data_type=QuestionDataType.EMAIL,
            )
            q7 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429a"),
                data_type=QuestionDataType.URL,
            )
            q8 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429b"),
                data_type=QuestionDataType.CHECKBOXES,
                data_source__items=[],
            )

            q8.data_source.items = [
                factories.data_source_item.build(data_source=q8.data_source, key=key, label=label)
                for key, label in [("cheddar", "Cheddar"), ("brie", "Brie"), ("stilton", "Stilton")]
            ]
            q9 = factories.question.build(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429c"),
                data_type=QuestionDataType.DATE,
            )

            submission = factories.submission.build(
                collection=form.collection,
                data={
                    str(q1.id): TextSingleLineAnswer("answer").get_value_for_submission(),
                    str(q2.id): TextMultiLineAnswer("answer\nthis").get_value_for_submission(),
                    str(q3.id): IntegerAnswer(value=50).get_value_for_submission(),
                    str(q4.id): YesNoAnswer(True).get_value_for_submission(),  # ty: ignore[missing-argument]
                    str(q5.id): SingleChoiceFromListAnswer(key="my-key", label="My label").get_value_for_submission(),
                    str(q6.id): TextSingleLineAnswer("name@example.com").get_value_for_submission(),
                    str(q7.id): TextSingleLineAnswer("https://example.com").get_value_for_submission(),
                    str(q8.id): MultipleChoiceFromListAnswer(
                        choices=[{"key": "cheddar", "label": "Cheddar"}, {"key": "stilton", "label": "Stilton"}]
                    ).get_value_for_submission(),
                    str(q9.id): DateAnswer(answer=date(2000, 1, 1)).get_value_for_submission(),
                },
            )
            helper = SubmissionHelper(submission)

            assert helper.cached_evaluation_context == ExpressionContext(
                submission_data={
                    "q_d696aebc49d24170a92fb6ef42994294": "answer",
                    "q_d696aebc49d24170a92fb6ef42994295": "answer\nthis",
                    "q_d696aebc49d24170a92fb6ef42994296": 50,
                    "q_d696aebc49d24170a92fb6ef42994297": True,
                    "q_d696aebc49d24170a92fb6ef42994298": "my-key",
                    "q_d696aebc49d24170a92fb6ef42994299": "name@example.com",
                    "q_d696aebc49d24170a92fb6ef4299429a": "https://example.com",
                    "q_d696aebc49d24170a92fb6ef4299429b": {"cheddar", "stilton"},
                    "q_d696aebc49d24170a92fb6ef4299429c": date(2000, 1, 1),
                }
            )

        def test_with_add_another_groups(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=2,
            )
            questions = collection.forms[0].cached_questions
            helper = SubmissionHelper(collection.test_submissions[0])

            assert helper.cached_evaluation_context == ExpressionContext(
                submission_data={
                    f"{questions[0].safe_qid}": "test name",
                    f"{questions[1].safe_qid}": "test org name",
                    f"{questions[2].safe_qid}": ["test name 0", "test name 1"],
                    f"{questions[3].safe_qid}": ["test_user_0@email.com", "test_user_1@email.com"],
                    f"{questions[4].safe_qid}": 3,
                }
            )

    class TestStatuses:
        def test_form_status_based_on_questions(self, db_session, factories):
            form = factories.form.build()
            form_two = factories.form.build(collection=form.collection)
            question_one = factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            question_two = factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            question_three = factories.question.build(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296")
            )

            submission = factories.submission.build(collection=form.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.NOT_STARTED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question_one.id,
                build_question_form([question_one], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form([question_two], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994295="User submitted data"
                ),
            )

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.IN_PROGRESS

            helper.toggle_form_completed(form, submission.created_by, True)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.COMPLETED

            # make sure the second form is unaffected by the first forms status
            helper.submit_answer_for_question(
                question_three.id,
                build_question_form([question_three], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994296="User submitted data"
                ),
            )
            assert helper.get_status_for_form(form_two) == SubmissionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form_two) == TasklistTaskStatusEnum.IN_PROGRESS

        def test_form_status_with_no_questions(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.collection)
            helper = SubmissionHelper(submission)
            assert helper.get_status_for_form(form) == SubmissionStatusEnum.NOT_STARTED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.NO_QUESTIONS

        def test_submission_status_based_on_forms(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            form_two = factories.form.build(collection=question.form.collection)
            question_two = factories.question.build(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))

            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistTaskStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form([question_two], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994295="User submitted data"
                ),
            )
            helper.toggle_form_completed(question_two.form, submission.created_by, True)

            assert helper.get_status_for_form(question_two.form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question_two.form) == TasklistTaskStatusEnum.COMPLETED

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit(submission.created_by)

            assert helper.status == SubmissionStatusEnum.COMPLETED

        def test_toggle_form_status(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            form = question.form
            submission = factories.submission.build(collection=form.collection)
            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.toggle_form_completed(form, submission.created_by, True)

            assert str(e.value) == AnyStringMatching(
                r"Could not mark form id=[a-z0-9-]+ as complete because not all questions have been answered."
            )

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(form, submission.created_by, True)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.COMPLETED

        def test_toggle_form_status_doesnt_change_status_if_already_completed(self, db_session, factories):
            collection = factories.collection.build()
            form = factories.form.build(collection=collection)

            # a second form with questions ensures nothing is conflating the submission and individual form statuses
            second_form = factories.form.build(collection=collection)

            question = factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.build(form=second_form)

            submission = factories.submission.build(collection=collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistTaskStatusEnum.COMPLETED

            helper.toggle_form_completed(question.form, submission.created_by, True)
            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistTaskStatusEnum.COMPLETED
            assert len(submission.events) == 1

        def test_submit_submission_rejected_if_not_complete(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )

            with pytest.raises(ValueError) as e:
                helper.submit(submission.created_by)

            assert str(e.value) == AnyStringMatching(
                r"Could not submit submission id=[a-z0-9-]+ because not all forms are complete."
            )

    class TestGetAnswerForQuestion:
        def test_get_answer_for_question(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_each_question_type__test=1,
                create_completed_submissions_each_question_type__use_random_data=False,
            )
            helper = SubmissionHelper(collection.test_submissions[0])

            question = collection.forms[0].cached_questions[0]

            answer = helper._get_answer_for_question(question.id)
            assert answer == TextSingleLineAnswer("test name")

        def test_get_answer_for_question_not_answered(self, factories, mocker):
            collection = factories.collection.create(
                create_completed_submissions_each_question_type__test=1,
                create_completed_submissions_each_question_type__use_random_data=False,
            )
            question = collection.forms[0].cached_questions[0]
            collection.test_submissions[0].data[str(question.id)] = None

            helper = SubmissionHelper(collection.test_submissions[0])
            answer = helper._get_answer_for_question(question.id)

            assert answer is None

        def test_get_answer_for_add_another_question_group_no_answer(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=0,
            )

            helper = SubmissionHelper(collection.test_submissions[0])
            question = collection.forms[0].cached_questions[2]
            assert question.add_another_container is not None
            assert helper._get_answer_for_question(question.id) == []

        def test_get_answer_for_add_another_question_group(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=2,
            )

            helper = SubmissionHelper(collection.test_submissions[0])
            question = collection.forms[0].cached_questions[2]
            assert question.add_another_container is not None
            assert helper._get_answer_for_question(question_id=question.id) == [
                TextSingleLineAnswer("test name 0"),
                TextSingleLineAnswer("test name 1"),
            ]


class TestCollectionHelper:
    def test_init_collection_helper(self, factories):
        collection = factories.collection.create(create_submissions__test=2, create_submissions__live=3)
        collection_from_db = interfaces.collections.get_collection(collection.id)
        assert len(collection_from_db._submissions) == 5

        test_collection_helper = CollectionHelper(
            collection=collection_from_db, submission_mode=SubmissionModeEnum.TEST
        )
        assert test_collection_helper.collection == collection
        assert test_collection_helper.submission_mode == SubmissionModeEnum.TEST
        assert len(test_collection_helper.submissions) == 2

        live_collection_helper = CollectionHelper(
            collection=collection_from_db, submission_mode=SubmissionModeEnum.LIVE
        )
        assert live_collection_helper.collection == collection
        assert live_collection_helper.submission_mode == SubmissionModeEnum.LIVE
        assert len(live_collection_helper.submissions) == 3

    def test_generate_csv_content_check_correct_rows_for_multiple_simple_submissions_every_question_type(
        self, factories
    ):
        num_test_submissions = 3
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=num_test_submissions,
            create_completed_submissions_each_question_type__use_random_data=True,
        )
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.DictReader(StringIO(csv_content))

        assert reader.fieldnames == [
            "Submission reference",
            "Created by",
            "Created at",
            "Status",
            "Submitted at",
            "[Export test form] Your name",
            "[Export test form] Your quest",
            "[Export test form] Airspeed velocity",
            "[Export test form] Best option",
            "[Export test form] Like cheese",
            "[Export test form] Email address",
            "[Export test form] Website address",
            "[Export test form] Favourite cheeses",
            "[Export test form] Last cheese purchase date",
        ]
        expected_question_data = {}
        for _, submission in c_helper.submission_helpers.items():
            expected_question_data[submission.reference] = {
                f"[{question.form.title}] {question.name}": _deserialise_question_type(
                    question, submission.submission.data[str(question.id)]
                ).get_value_for_text_export()
                for _, question in submission.all_visible_questions.items()
            }
        rows = list(reader)
        for line in rows:
            submission_ref = line["Submission reference"]
            s_helper = c_helper.get_submission_helper_by_reference(submission_ref)
            assert line["Created by"] == s_helper.created_by_email
            assert line["Created at"] == format_datetime(s_helper.created_at_utc)
            for header, value in expected_question_data[submission_ref].items():
                assert line[header] == value

        assert len(rows) == num_test_submissions

    def test_generate_csv_content_skipped_questions(self, factories):
        collection = factories.collection.create(create_completed_submissions_conditional_question__test=True)
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.DictReader(StringIO(csv_content))

        assert reader.fieldnames == [
            "Submission reference",
            "Created by",
            "Created at",
            "Status",
            "Submitted at",
            "[Export test form] Number of cups of tea",
            "[Export test form] Tea bag pack size",
            "[Export test form] Favourite dunking biscuit",
        ]
        for _ in range(2):
            line = next(reader)
            submission_ref = line["Submission reference"]
            s_helper = c_helper.get_submission_helper_by_reference(submission_ref)
            assert line["Created by"] == s_helper.created_by_email
            assert line["Created at"] == format_datetime(s_helper.created_at_utc)
            number_of_cups_of_tea = line["[Export test form] Number of cups of tea"]
            if number_of_cups_of_tea == "40":
                assert line["[Export test form] Tea bag pack size"] == "80"
            elif number_of_cups_of_tea == "20":
                assert line["[Export test form] Tea bag pack size"] == NOT_ASKED
            else:
                pytest.fail("Unexpected number of cups of tea value: {number_of_cups_of_tea}")
            assert line["[Export test form] Favourite dunking biscuit"] == "digestive"

    def test_generate_csv_content_skipped_questions_previously_answered(self, factories):
        collection = factories.collection.create(create_completed_submissions_conditional_question__test=True)
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        dependant_question_id = collection.forms[0].cached_questions[0].id
        conditional_question_id = collection.forms[0].cached_questions[1].id

        # Find the submission where question 2 is not expected to be answered it and store some data as though it has
        # previously been answered
        submission = next(
            helper.submission
            for _, helper in c_helper.submission_helpers.items()
            if helper.cached_get_answer_for_question(dependant_question_id).get_value_for_text_export() == "20"
        )
        submission.data[str(conditional_question_id)] = IntegerAnswer(value=120).get_value_for_submission()
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.DictReader(StringIO(csv_content))

        assert reader.fieldnames == [
            "Submission reference",
            "Created by",
            "Created at",
            "Status",
            "Submitted at",
            "[Export test form] Number of cups of tea",
            "[Export test form] Tea bag pack size",
            "[Export test form] Favourite dunking biscuit",
        ]
        for _ in range(2):
            line = next(reader)
            number_of_cups_of_tea = line["[Export test form] Number of cups of tea"]
            # Check that one submission says NOT_ASKED for question 2 because based on the value of question 1
            # it should not be visible
            if number_of_cups_of_tea == "40":
                assert line["[Export test form] Tea bag pack size"] == "80"
            elif number_of_cups_of_tea == "20":
                assert line["[Export test form] Tea bag pack size"] == NOT_ASKED
            else:
                pytest.fail("Unexpected number of cups of tea value: {number_of_cups_of_tea}")

    def test_all_question_types_appear_correctly_in_csv_row(self, factories):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=1,
            create_completed_submissions_each_question_type__use_random_data=False,
        )
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 2

        assert rows[0] == [
            "Submission reference",
            "Created by",
            "Created at",
            "Status",
            "Submitted at",
            "[Export test form] Your name",
            "[Export test form] Your quest",
            "[Export test form] Airspeed velocity",
            "[Export test form] Best option",
            "[Export test form] Like cheese",
            "[Export test form] Email address",
            "[Export test form] Website address",
            "[Export test form] Favourite cheeses",
            "[Export test form] Last cheese purchase date",
        ]
        assert rows[1] == [
            c_helper.submissions[0].reference,
            c_helper.submissions[0].created_by.email,
            format_datetime(c_helper.submissions[0].created_at_utc),
            "In progress",
            "",
            "test name",
            "Line 1\r\nline2\r\nline 3",
            "123",
            "Option 0",
            "Yes",
            "test@email.com",
            "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government",
            "Cheddar\nStilton",
            "2025-01-01",
        ]

    def test_all_question_types_appear_correctly_in_json_export(self, factories):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=1,
            create_completed_submissions_each_question_type__use_random_data=False,
        )
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        json_data = c_helper.generate_json_content_for_all_submissions()
        submissions = json.loads(json_data)

        assert submissions == {
            "submissions": [
                {
                    "created_at_utc": mock.ANY,
                    "created_by": mock.ANY,
                    "reference": mock.ANY,
                    "status": "In progress",
                    "submitted_at_utc": None,
                    "tasks": [
                        {
                            "answers": {
                                "Airspeed velocity": {"value": 123},
                                "Best option": {"key": "key-0", "label": "Option 0"},
                                "Email address": "test@email.com",
                                "Favourite cheeses": [
                                    {"key": "cheddar", "label": "Cheddar"},
                                    {"key": "stilton", "label": "Stilton"},
                                ],
                                "Like cheese": True,
                                "Website address": "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government",
                                "Your name": "test name",
                                "Your quest": "Line 1\r\nline2\r\nline 3",
                                "Last cheese purchase date": "2025-01-01",
                            },
                            "name": "Export test form",
                        }
                    ],
                }
            ]
        }

    @pytest.mark.skip(reason="performance")
    @pytest.mark.parametrize("num_test_submissions", [1, 2, 3, 5, 12, 60, 100, 500])
    def test_multiple_submission_export_non_conditional(self, factories, track_sql_queries, num_test_submissions):
        """
        This test and the one below create a collection with a number of test submissions, then time how long it takes
        to generate the CSV content for all submissions. It also tracks the number of SQL queries made and their total
        duration.

        It is skipped as now we have improved the performance of the queries to generate the CSV file, the test doesn't
        record any queries as everything is already cached by the factory. Leaving it in the code for reference and
        future use. See 'Seeding for performance testing' in the README for more details.
        """
        factory_start = datetime.now()
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=num_test_submissions
        )
        factory_duration = datetime.now() - factory_start
        # FIXME Can we clear out the session cache here so we actually generate some queries?
        create_collection_helper_start = datetime.now()
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        create_collection_helper_duration = datetime.now() - create_collection_helper_start
        with track_sql_queries() as queries:
            start = datetime.now()
            c_helper.generate_csv_content_for_all_submissions()
            end = datetime.now()
            generate_csv_content_for_all_submissions_duration = end - start
        total_query_duration = sum(query.duration for query in queries)
        results = {
            "num_test_submissions": num_test_submissions,
            "num_sql_queries": len(queries),
            "factory_duration": str(factory_duration.total_seconds()),
            "create_collection_helper_duration": str(create_collection_helper_duration.total_seconds()),
            "total_query_duration": str(total_query_duration),
            "generate_csv_content_for_all_submissions_duration": str(
                generate_csv_content_for_all_submissions_duration.total_seconds()
            ),
        }
        header_string = ",".join(results.keys())
        print(header_string)
        result_string = ",".join([str(results.get(header)) for header in header_string.split(",")])
        print(result_string)

        assert len(queries) == 12

    @pytest.mark.skip(reason="performance")
    @pytest.mark.parametrize("num_test_submissions", [1, 2, 3, 5, 12, 60, 100, 500])
    def test_multiple_submission_export_conditional(self, factories, track_sql_queries, num_test_submissions):
        """
        As with the test above, this test create a collection with a number of test submissions, then times how long it
        takes to generate the CSV content for all submissions. It also tracks the number of SQL queries made and their
        total duration.

        It is skipped as now we have improved the performance of the queries to generate the CSV file, the test doesn't
        record any queries as everything is already cached by the factory. Leaving it in the code for reference and
        future use. See 'Seeding for performance testing' in the README for more details.
        """
        factory_start = datetime.now()
        collection = factories.collection.create(
            create_completed_submissions_conditional_question_random__test=num_test_submissions
        )
        factory_duration = datetime.now() - factory_start
        create_collection_helper_start = datetime.now()
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        create_collection_helper_duration = datetime.now() - create_collection_helper_start
        with track_sql_queries() as queries:
            start = datetime.now()
            c_helper.generate_csv_content_for_all_submissions()
            end = datetime.now()
            generate_csv_content_for_all_submissions_duration = end - start
        total_query_duration = sum(query.duration for query in queries)
        results = {
            "num_test_submissions": num_test_submissions,
            "num_sql_queries": len(queries),
            "factory_duration": str(factory_duration.total_seconds()),
            "create_collection_helper_duration": str(create_collection_helper_duration.total_seconds()),
            "total_query_duration": str(total_query_duration),
            "generate_csv_content_for_all_submissions_duration": str(
                generate_csv_content_for_all_submissions_duration.total_seconds()
            ),
        }
        header_string = ",".join(results.keys())
        print(header_string)
        result_string = ",".join([str(results.get(header)) for header in header_string.split(",")])
        print(result_string)

        assert len(queries) == 12

    class TestQuestionVisibilityWithAddAnother:
        def test_collection_setup(self, factories):  # collection_with_add_another_submissions):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group_with_conditions__test=1
            )
            submission = collection.test_submissions[0]
            assert submission.data == {
                str(collection.park_name_question.id): "No play equipment, No trees",
                str(collection.has_trees_question.id): False,
                str(collection.has_equipment_question.id): False,
            }

        @pytest.mark.parametrize(
            "park_name, expected",
            [
                ("No play equipment, No trees", False),
                ("No play equipment, Has trees", False),
                ("Has play equipment, No trees", True),
                ("Has play equipment, Has trees", True),
            ],
        )
        def test_is_component_visible_simple_condition_inside_group(self, factories, park_name, expected):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group_with_conditions__test=1
            )
            submission = next(
                submission
                for submission in collection.test_submissions
                if submission.data[str(collection.park_name_question.id)] == park_name
            )
            assert submission
            helper = SubmissionHelper(submission)
            assert (
                helper.is_component_visible(collection.equipment_number_question, helper.cached_evaluation_context)
                == expected
            )
            assert helper.is_component_visible(collection.equipment_group, helper.cached_evaluation_context) == expected

        @pytest.mark.parametrize(
            "park_name, expected",
            [
                ("No play equipment, No trees", False),
                ("No play equipment, Has trees", False),
                ("Has play equipment, No trees", True),
                ("Has play equipment, Has trees", True),
            ],
        )
        def test_is_component_visible_simple_condition(self, factories, park_name, expected):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group_with_conditions__test=1
            )
            submission = next(
                submission
                for submission in collection.test_submissions
                if submission.data[str(collection.park_name_question.id)] == park_name
            )
            assert submission
            helper = SubmissionHelper(submission)
            assert (
                helper.is_component_visible(collection.fenced_off_question, helper.cached_evaluation_context)
                == expected
            )

        @pytest.mark.parametrize(
            "park_name, expected",
            [
                ("No play equipment, No trees", False),
                ("No play equipment, Has trees", True),
                ("Has play equipment, No trees", False),
                ("Has play equipment, Has trees", True),
            ],
        )
        def test_is_component_visible_simple_condition_inside_add_another_group(self, factories, park_name, expected):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group_with_conditions__test=1
            )
            submission = next(
                submission
                for submission in collection.test_submissions
                if submission.data[str(collection.park_name_question.id)] == park_name
            )
            assert submission
            helper = SubmissionHelper(submission)
            assert (
                helper.is_component_visible(collection.tree_species_question, helper.cached_evaluation_context)
                == expected
            )
            assert (
                helper.is_component_visible(collection.under_a_tree_question, helper.cached_evaluation_context)
                == expected
            )

        @pytest.mark.parametrize(
            "park_name, add_another_index, expected",
            [
                ("Has play equipment, No trees", 0, False),
                ("Has play equipment, No trees", 1, False),
                ("Has play equipment, No trees", 2, True),
                ("Has play equipment, Has trees", 0, False),
                ("Has play equipment, Has trees", 1, False),
                ("Has play equipment, Has trees", 2, True),
            ],
        )
        @pytest.mark.skip(reason="Not implemented")
        def test_is_component_visible_condition_inside_add_another_group_dependency_within_group(
            self, factories, park_name, add_another_index, expected
        ):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group_with_conditions__test=1
            )
            submission = next(
                submission
                for submission in collection.test_submissions
                if submission.data[str(collection.park_name_question.id)] == park_name
            )
            assert submission
            helper = SubmissionHelper(submission)
            assert (
                helper.is_component_visible(
                    collection.other_equipment_question,
                    helper.cached_evaluation_context,
                    add_another_index=add_another_index,
                )
                == expected
            )
            assert (
                helper.is_component_visible(collection.under_a_tree_question, helper.cached_evaluation_context) is True
            )
