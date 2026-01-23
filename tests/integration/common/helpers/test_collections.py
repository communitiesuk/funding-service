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
from app.common.data.interfaces.collections import add_question_validation
from app.common.data.types import (
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistSectionStatusEnum,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import GreaterThan
from app.common.filters import format_datetime
from app.common.helpers.collections import (
    CollectionHelper,
    SubmissionAuthorisationError,
    SubmissionHelper,
    _deserialise_question_type,
)
from tests.utils import AnyStringMatching

EC = ExpressionContext


class TestSubmissionHelper:
    class TestGetAndSubmitAnswerForQuestion:
        def test_submit_valid_data(self, db_session, factories):
            question = factories.question.create(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.cached_get_answer_for_question(question.id) is None

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="User submitted data"
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("User submitted data")

        def test_get_data_maps_type(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.INTEGER
            )
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294=5
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.cached_get_answer_for_question(question.id) == IntegerAnswer(value=5)

        def test_can_get_falsey_answers(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.INTEGER
            )
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294=0
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.cached_get_answer_for_question(question.id) == IntegerAnswer(value=0)

        def test_cannot_submit_answer_on_submitted_submission(self, db_session, factories, submission_submitted):
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED

            question = submission_submitted.collection.forms[0].cached_questions[0]
            form = build_question_form(
                [question],
                evaluation_context=EC(),
                interpolation_context=EC(),
            )(q_d696aebc49d24170a92fb6ef42994294="User submitted data")

            with pytest.raises(ValueError) as e:
                helper.submit_answer_for_question(submission_submitted.collection.forms[0].cached_questions[0].id, form)

            assert str(e.value) == AnyStringMatching(
                "Could not submit answer for question_id=[a-z0-9-]+ "
                "because submission id=[a-z0-9-]+ is already submitted."
            )

    class TestFormData:
        def test_no_submission_data(self, factories):
            form = factories.form.create()
            form_two = factories.form.create(collection=form.collection)
            factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            factories.question.create(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"))

            submission = factories.submission.create(collection=form.collection)
            helper = SubmissionHelper(submission)

            assert helper.form_data() == {}

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 9, "Update this test if adding new questions"

            form = factories.form.create()
            form_two = factories.form.create(collection=form.collection)
            q1 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            )
            q2 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"),
                data_type=QuestionDataType.TEXT_MULTI_LINE,
            )
            q3 = factories.question.create(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"), data_type=QuestionDataType.INTEGER
            )
            q4 = factories.question.create(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994297"), data_type=QuestionDataType.YES_NO
            )
            q5 = factories.question.create(
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994298"),
                data_type=QuestionDataType.RADIOS,
                data_source__items=[],
            )
            q5.data_source.items = [
                factories.data_source_item.create(data_source=q5.data_source, key=key, label=label)
                for key, label in [("key-1", "Key 1"), ("key-2", "Key 2")]
            ]
            q6 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994299"),
                data_type=QuestionDataType.EMAIL,
            )
            q7 = factories.question.create(
                form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429a"), data_type=QuestionDataType.URL
            )
            q8 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429b"),
                data_type=QuestionDataType.CHECKBOXES,
                data_source__items=[],
            )
            q8.data_source.items = [
                factories.data_source_item.create(data_source=q8.data_source, key=key, label=label)
                for key, label in [("cheddar", "Cheddar"), ("brie", "Brie"), ("stilton", "Stilton")]
            ]
            q9 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429c"),
                data_type=QuestionDataType.DATE,
            )

            submission = factories.submission.create(
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

            assert helper.form_data() == {
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

        def test_with_add_another_groups_no_context(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=2,
            )
            questions = collection.forms[0].cached_questions
            helper = SubmissionHelper(collection.test_submissions[0])

            assert helper.form_data() == {
                f"{questions[0].safe_qid}": "test name",
                f"{questions[1].safe_qid}": "test org name",
                f"{questions[4].safe_qid}": 3,
            }

        def test_with_add_another_group_with_context(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=2,
            )
            questions = collection.forms[0].cached_questions
            helper = SubmissionHelper(collection.test_submissions[0])

            add_another_container = questions[2].add_another_container

            assert helper.form_data(add_another_container=add_another_container, add_another_index=0) == {
                f"{questions[0].safe_qid}": "test name",
                f"{questions[1].safe_qid}": "test org name",
                f"{questions[2].safe_qid}": "test name 0",
                f"{questions[3].safe_qid}": "test_user_0@email.com",
                f"{questions[4].safe_qid}": 3,
            }

            assert helper.form_data(add_another_container=add_another_container, add_another_index=1) == {
                f"{questions[0].safe_qid}": "test name",
                f"{questions[1].safe_qid}": "test org name",
                f"{questions[2].safe_qid}": "test name 1",
                f"{questions[3].safe_qid}": "test_user_1@email.com",
                f"{questions[4].safe_qid}": 3,
            }

    class TestExpressionContext:
        def test_no_submission_data(self, factories):
            form = factories.form.create()
            form_two = factories.form.create(collection=form.collection)
            factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            factories.question.create(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"))

            submission = factories.submission.create(collection=form.collection)
            helper = SubmissionHelper(submission)

            assert helper.cached_evaluation_context == ExpressionContext(
                {
                    "data": {},
                    "submissions": {form.collection.safe_cid: {}},
                }
            )

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 9, "Update this test if adding new questions"

            form = factories.form.create()
            form_two = factories.form.create(collection=form.collection)
            q1 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            )
            q2 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"),
                data_type=QuestionDataType.TEXT_MULTI_LINE,
            )
            q3 = factories.question.create(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"), data_type=QuestionDataType.INTEGER
            )
            q4 = factories.question.create(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994297"), data_type=QuestionDataType.YES_NO
            )
            q5 = factories.question.create(
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994298"),
                data_type=QuestionDataType.RADIOS,
                data_source__items=[],
            )
            q5.data_source.items = [
                factories.data_source_item.create(data_source=q5.data_source, key=key, label=label)
                for key, label in [("key-1", "Key 1"), ("key-2", "Key 2")]
            ]
            q6 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994299"),
                data_type=QuestionDataType.EMAIL,
            )
            q7 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429a"),
                data_type=QuestionDataType.URL,
            )
            q8 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429b"),
                data_type=QuestionDataType.CHECKBOXES,
                data_source__items=[],
            )

            q8.data_source.items = [
                factories.data_source_item.create(data_source=q8.data_source, key=key, label=label)
                for key, label in [("cheddar", "Cheddar"), ("brie", "Brie"), ("stilton", "Stilton")]
            ]
            q9 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429c"),
                data_type=QuestionDataType.DATE,
            )

            submission = factories.submission.create(
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
                    "data": {},
                    "submissions": {
                        form.collection.safe_cid: {
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
                    },
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
                    "data": {},
                    "submissions": {
                        collection.safe_cid: {
                            f"{questions[0].safe_qid}": "test name",
                            f"{questions[1].safe_qid}": "test org name",
                            f"{questions[4].safe_qid}": 3,
                        }
                    },
                    f"{questions[0].safe_qid}": "test name",
                    f"{questions[1].safe_qid}": "test org name",
                    f"{questions[4].safe_qid}": 3,
                }
            )

    class TestStatuses:
        def test_form_status_based_on_questions(self, db_session, factories):
            form = factories.form.create()
            form_two = factories.form.create(collection=form.collection)
            question_one = factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            question_two = factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            question_three = factories.question.create(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296")
            )

            submission = factories.submission.create(collection=form.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.NOT_STARTED
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question_one.id,
                build_question_form([question_one], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )

            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form([question_two], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994295="User submitted data"
                ),
            )

            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

            helper.toggle_form_completed(form, submission.created_by, True)

            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

            # make sure the second form is unaffected by the first forms status
            helper.submit_answer_for_question(
                question_three.id,
                build_question_form([question_three], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994296="User submitted data"
                ),
            )
            assert helper.get_status_for_form(form_two) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form_two) == TasklistSectionStatusEnum.IN_PROGRESS

        def test_form_status_with_no_questions(self, db_session, factories):
            form = factories.form.create()
            submission = factories.submission.create(collection=form.collection)
            helper = SubmissionHelper(submission)
            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.NOT_STARTED
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.NO_QUESTIONS

        def test_submission_status_based_on_forms(self, db_session, factories, mock_notification_service_calls):
            org = factories.organisation.create()
            grant = factories.grant.create()
            gr = factories.grant_recipient.create(organisation=org, grant=grant)
            certifier = factories.user.create()
            factories.user_role.create(
                user=certifier,
                organisation=org,
                permissions=[RoleEnum.CERTIFIER],
            )
            collection = factories.collection.create(
                grant=grant, reporting_period_start_date=date(2025, 1, 1), reporting_period_end_date=date(2025, 3, 31)
            )
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), form__collection=collection
            )
            form_two = factories.form.create(collection=collection)
            question_two = factories.question.create(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295")
            )

            submission = factories.submission.create(collection=question.form.collection, grant_recipient=gr)
            helper = SubmissionHelper(submission)

            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form([question_two], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994295="User submitted data"
                ),
            )
            helper.toggle_form_completed(question_two.form, submission.created_by, True)

            assert helper.get_status_for_form(question_two.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question_two.form) == TasklistSectionStatusEnum.COMPLETED

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.mark_as_sent_for_certification(submission.created_by)

            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
            assert helper.events.submission_state.is_awaiting_sign_off is True
            assert helper.events.submission_state.sent_for_certification_by is submission.created_by

            helper.decline_certification(certifier, "Reason for declining")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            assert helper.events.submission_state.sent_for_certification_by is submission.created_by
            assert helper.events.submission_state.is_awaiting_sign_off is False
            assert helper.events.submission_state.declined_by == certifier
            assert helper.events.submission_state.declined_reason == "Reason for declining"

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_status_for_form(question_two.form) == TasklistSectionStatusEnum.IN_PROGRESS

            helper.toggle_form_completed(question.form, submission.created_by, True)
            helper.toggle_form_completed(question_two.form, submission.created_by, True)

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.mark_as_sent_for_certification(submission.created_by)

            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            helper.certify(certifier)

            assert helper.events.submission_state.is_awaiting_sign_off is False
            assert helper.events.submission_state.is_approved is True
            assert helper.events.submission_state.certified_by == certifier

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.submit(certifier)

            assert helper.status == SubmissionStatusEnum.SUBMITTED
            assert helper.events.submission_state.submitted_by == certifier
            assert helper.events.submission_state.is_approved is True
            assert helper.events.submission_state.is_awaiting_sign_off is False

        def test_toggle_form_status(self, db_session, factories):
            question = factories.question.create(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            form = question.form
            submission = factories.submission.create(collection=form.collection)
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

            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

        def test_toggle_form_status_doesnt_change_status_if_already_completed(self, db_session, factories):
            collection = factories.collection.create()
            form = factories.form.create(collection=collection)

            # a second form with questions ensures nothing is conflating the submission and individual form statuses
            second_form = factories.form.create(collection=collection)

            question = factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.create(form=second_form)

            submission = factories.submission.create(collection=collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED

            helper.toggle_form_completed(question.form, submission.created_by, True)
            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert len(submission.events) == 1

        def test_submit_submission_rejected_if_not_complete(self, db_session, factories):
            question = factories.question.create(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            submission = factories.submission.create(collection=question.form.collection)

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

    class TestRequiresCertification:
        def test_decline_certification_requires_certification(self, factories, submission_awaiting_sign_off, user):
            collection = submission_awaiting_sign_off.collection
            collection.requires_certification = False
            with pytest.raises(ValueError) as e:
                SubmissionHelper(submission_awaiting_sign_off).decline_certification(
                    user=user, declined_reason="test reason"
                )
            assert (
                str(e.value)
                == f"Could not decline certification for submission id={submission_awaiting_sign_off.id} because this "
                f"report does not require certification."
            )

        def test_certify_requires_certification(self, factories, submission_awaiting_sign_off, user):
            collection = submission_awaiting_sign_off.collection
            collection.requires_certification = False
            with pytest.raises(ValueError) as e:
                SubmissionHelper(submission_awaiting_sign_off).certify(user)
            assert (
                str(e.value)
                == f"Could not approve certification for submission id={submission_awaiting_sign_off.id} because this "
                f"report does not require certification."
            )

        def test_send_for_sign_off_requires_certification(self, factories, submission_in_progress, user):
            collection = submission_in_progress.collection
            collection.requires_certification = False
            with pytest.raises(ValueError) as e:
                SubmissionHelper(submission_in_progress).mark_as_sent_for_certification(user)
            assert (
                str(e.value)
                == f"Could not send submission id={submission_in_progress.id} for sign off because this report does "
                f"not require certification."
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

        def test_get_answer_for_add_another_question_group_missing_index(self, factories):
            group = factories.group.create(add_another=True)
            question = factories.question.create(form=group.form, parent=group)
            submission = factories.submission.create(collection=group.form.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                helper._get_answer_for_question(question_id=question.id)
            assert str(e.value) == "add_another_index must be provided for questions within an add another container"

        def test_get_answer_for_add_another_question_group_invalid_idnex(self, factories):
            group = factories.group.create(add_another=True)
            question = factories.question.create(form=group.form, parent=group)
            submission = factories.submission.create(collection=group.form.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                helper._get_answer_for_question(question_id=question.id, add_another_index=0)
            assert str(e.value) == "no add another entry exists at this index"

        def test_get_answer_for_add_another_question_group_at_index(self, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
            )

            helper = SubmissionHelper(collection.test_submissions[0])
            question = collection.forms[0].cached_questions[2]
            assert question.add_another_container is not None
            assert helper._get_answer_for_question(
                question_id=question.id, add_another_index=0
            ) == TextSingleLineAnswer("test name 0")
            assert helper._get_answer_for_question(
                question_id=question.id, add_another_index=1
            ) == TextSingleLineAnswer("test name 1")

    class TestAuthenticationChecksInMethods:
        def test_decline_certification_auth_check_errors_correctly(self, mocker, submission_awaiting_sign_off):
            helper = SubmissionHelper(submission_awaiting_sign_off)
            submitter_user = helper.sent_for_certification_by

            with pytest.raises(SubmissionAuthorisationError) as error:
                helper.decline_certification(submitter_user, "Decline reason")

            assert error.value.user == submitter_user
            assert error.value.submission_id == submission_awaiting_sign_off.id
            assert error.value.required_permission == RoleEnum.CERTIFIER
            assert "User does not have certifier permission to decline submission" in error.value.message

        def test_certify_submission_auth_check_errors_correctly(self, submission_awaiting_sign_off):
            helper = SubmissionHelper(submission_awaiting_sign_off)
            submitter_user = helper.sent_for_certification_by

            with pytest.raises(SubmissionAuthorisationError) as error:
                helper.certify(submitter_user)

            assert error.value.user == submitter_user
            assert error.value.submission_id == submission_awaiting_sign_off.id
            assert error.value.required_permission == RoleEnum.CERTIFIER
            assert "User does not have certifier permission to certify submission" in error.value.message

        def test_submit_submission_auth_check_errors_correctly(self, submission_awaiting_sign_off, factories):
            helper = SubmissionHelper(submission_awaiting_sign_off)
            submitter_user = helper.sent_for_certification_by
            certifier_user = factories.user.create()
            factories.user_role.create(
                user=certifier_user,
                organisation=submission_awaiting_sign_off.grant_recipient.organisation,
                grant=helper.grant,
                permissions=[RoleEnum.CERTIFIER],
            )

            factories.submission_event.create(
                submission=submission_awaiting_sign_off,
                event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
                created_by=certifier_user,
                created_at_utc=datetime(2025, 12, 1, 0, 0, 0),
            )

            with pytest.raises(SubmissionAuthorisationError) as error:
                helper.submit(submitter_user)

            assert error.value.user == submitter_user
            assert error.value.submission_id == submission_awaiting_sign_off.id
            assert error.value.required_permission == RoleEnum.CERTIFIER
            assert "User does not have certifier permission to submit submission" in error.value.message

        def test_submit_submission_auth_check_allows_test_submission(
            self, submission_awaiting_sign_off, factories, mock_notification_service_calls
        ):
            helper = SubmissionHelper(submission_awaiting_sign_off)
            submission_awaiting_sign_off.mode = SubmissionModeEnum.TEST

            submitter_user = helper.sent_for_certification_by
            certifier_user = factories.user.create()
            factories.user_role.create(
                user=certifier_user,
                organisation=submission_awaiting_sign_off.grant_recipient.organisation,
                grant=helper.grant,
                permissions=[RoleEnum.CERTIFIER],
            )

            factories.submission_event.create(
                submission=submission_awaiting_sign_off,
                event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
                created_by=certifier_user,
                created_at_utc=datetime(2025, 12, 1, 0, 0, 0),
            )
            assert len(helper.submission.events) == 3

            helper.submit(submitter_user)

            assert len(helper.submission.events) == 4
            assert helper.status == SubmissionStatusEnum.SUBMITTED

        def test_submit_submission_auth_check_allows_live_submissions_where_certification_not_needed(
            self, submission_ready_to_submit, factories, mock_notification_service_calls, data_provider_user
        ):
            helper = SubmissionHelper(submission_ready_to_submit)
            submission_ready_to_submit.collection.requires_certification = False
            assert len(helper.submission.events) == 1

            helper.submit(data_provider_user)

            assert len(helper.submission.events) == 2
            assert helper.status == SubmissionStatusEnum.SUBMITTED

    class TestSubmit:
        def test_submit_when_requires_certification(
            self,
            submission_awaiting_sign_off,
            factories,
            data_provider_user,
            mock_notification_service_calls,
            user,
            certifier_user,
        ):
            collection = submission_awaiting_sign_off.collection
            assert collection.requires_certification is True
            helper = SubmissionHelper(submission_awaiting_sign_off)
            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            factories.submission_event.create(
                created_by=certifier_user,
                created_at_utc=datetime(2025, 12, 1, 0, 0, 0),
                related_entity_id=submission_awaiting_sign_off.id,
                submission=submission_awaiting_sign_off,
                event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
            )
            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.submit(user=certifier_user)

            assert helper.status == SubmissionStatusEnum.SUBMITTED
            assert len(mock_notification_service_calls) == 2

        def test_submit_when_sign_off_not_required(
            self, submission_ready_to_submit, factories, mock_notification_service_calls, data_provider_user
        ):
            collection = submission_ready_to_submit.collection
            collection.requires_certification = False

            helper = SubmissionHelper(submission_ready_to_submit)
            assert helper.collection.requires_certification is False
            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.submit(user=data_provider_user)

            assert helper.status == SubmissionStatusEnum.SUBMITTED
            assert len(mock_notification_service_calls) == 1

        @pytest.mark.parametrize("requires_certification", (True, False))
        def test_submit_forms_not_complete(
            self, submission_in_progress, mock_notification_service_calls, data_provider_user, requires_certification
        ):
            submission_in_progress.collection.requires_certification = requires_certification
            helper = SubmissionHelper(submission_in_progress)
            with pytest.raises(ValueError) as e:
                helper.submit(data_provider_user)
            assert (
                str(e.value)
                == f"Could not submit submission id={submission_in_progress.id} because not all forms are complete."
            )
            assert len(mock_notification_service_calls) == 0

        @pytest.mark.parametrize("requires_certification", (True, False))
        def test_submit_not_ready_to_submit(
            self,
            submission_awaiting_sign_off,
            mock_notification_service_calls,
            data_provider_user,
            requires_certification,
        ):
            submission_awaiting_sign_off.collection.requires_certification = requires_certification
            helper = SubmissionHelper(submission_awaiting_sign_off)
            with pytest.raises(ValueError) as e:
                helper.submit(data_provider_user)
            assert (
                str(e.value) == f"Could not submit submission id={submission_awaiting_sign_off.id} "
                "because it is not ready to submit."
            )
            assert len(mock_notification_service_calls) == 0

        def test_submit_user_is_not_certifier(
            self,
            submission_awaiting_sign_off,
            mock_notification_service_calls,
            data_provider_user,
            certifier_user,
            factories,
        ):
            helper = SubmissionHelper(submission_awaiting_sign_off)

            factories.submission_event.create(
                created_by=certifier_user,
                created_at_utc=datetime(2025, 12, 1, 0, 0, 0),
                related_entity_id=submission_awaiting_sign_off.id,
                submission=submission_awaiting_sign_off,
                event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
            )
            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
            with pytest.raises(SubmissionAuthorisationError) as e:
                helper.submit(data_provider_user)
            assert (
                str(e.value)
                == f"User does not have certifier permission to submit submission {submission_awaiting_sign_off.id}"
            )
            assert len(mock_notification_service_calls) == 0

        def test_submit_sends_no_emails_and_succeeds_for_preview(
            self,
            submission_ready_to_submit,
            mock_notification_service_calls,
            data_provider_user,
        ):
            submission_ready_to_submit.mode = SubmissionModeEnum.PREVIEW
            helper = SubmissionHelper(submission_ready_to_submit)

            helper.submit(user=data_provider_user)

            assert helper.status == SubmissionStatusEnum.SUBMITTED
            assert len(mock_notification_service_calls) == 0

    class TestSentForCertification:
        def test_mark_as_sent_for_certification(
            self, data_provider_user, certifier_user, submission_ready_to_submit, mock_notification_service_calls
        ) -> None:
            helper = SubmissionHelper(submission_ready_to_submit)
            assert helper.collection.requires_certification is True
            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.mark_as_sent_for_certification(user=data_provider_user)

            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
            assert len(mock_notification_service_calls) == 2

    class TestCertificationApproved:
        def test_certify(
            self, data_provider_user, certifier_user, submission_awaiting_sign_off, mock_notification_service_calls
        ) -> None:
            helper = SubmissionHelper(submission_awaiting_sign_off)
            assert helper.collection.requires_certification is True
            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            helper.certify(user=certifier_user)

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
            assert len(mock_notification_service_calls) == 0

    class TestCertificationDeclined:
        def test_decline(
            self, data_provider_user, certifier_user, submission_awaiting_sign_off, mock_notification_service_calls
        ) -> None:
            helper = SubmissionHelper(submission_awaiting_sign_off)
            assert helper.collection.requires_certification is True
            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            helper.decline_certification(user=certifier_user, declined_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            # TODO should we change the decline function to send emails for consistency with submit/certify
            assert len(mock_notification_service_calls) == 0


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
            "Grant recipient",
            "Created by",
            "Created at",
            "Certified by",
            "Certified at",
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
            "Grant recipient",
            "Created by",
            "Created at",
            "Certified by",
            "Certified at",
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
            "Grant recipient",
            "Created by",
            "Created at",
            "Certified by",
            "Certified at",
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
            "Grant recipient",
            "Created by",
            "Created at",
            "Certified by",
            "Certified at",
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
            c_helper.submissions[0].grant_recipient.organisation.name,
            c_helper.submissions[0].created_by.email,
            format_datetime(c_helper.submissions[0].created_at_utc),
            "",
            "",
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

    def test_generate_csv_content_add_another(self, factories):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.DictReader(StringIO(csv_content))

        assert reader.fieldnames == [
            "Submission reference",
            "Grant recipient",
            "Created by",
            "Created at",
            "Certified by",
            "Certified at",
            "Status",
            "Submitted at",
            "[Add another nested group test form] Your name",
            "[Add another nested group test form] Organisation name",
            "[Add another nested group test form] [Organisation contacts test group] Contact name (1)",
            "[Add another nested group test form] [Organisation contacts test group] Contact email (1)",
            "[Add another nested group test form] [Organisation contacts test group] Contact name (2)",
            "[Add another nested group test form] [Organisation contacts test group] Contact email (2)",
            "[Add another nested group test form] [Organisation contacts test group] Contact name (3)",
            "[Add another nested group test form] [Organisation contacts test group] Contact email (3)",
            "[Add another nested group test form] [Organisation contacts test group] Contact name (4)",
            "[Add another nested group test form] [Organisation contacts test group] Contact email (4)",
            "[Add another nested group test form] [Organisation contacts test group] Contact name (5)",
            "[Add another nested group test form] [Organisation contacts test group] Contact email (5)",
            "[Add another nested group test form] Length of service",
        ]
        rows = list(reader)

        assert list(rows[0].values()) == [
            c_helper.submissions[0].reference,
            c_helper.submissions[0].grant_recipient.organisation.name,
            c_helper.submissions[0].created_by.email,
            format_datetime(c_helper.submissions[0].created_at_utc),
            "",
            "",
            "In progress",
            "",
            "test name",
            "test org name",
            "test name 0",
            "test_user_0@email.com",
            "test name 1",
            "test_user_1@email.com",
            "test name 2",
            "test_user_2@email.com",
            "test name 3",
            "test_user_3@email.com",
            "test name 4",
            "test_user_4@email.com",
            "3",
        ]

    def test_generate_csv_content_add_another_handles_different_answer_list_sizes(self, factories):
        group = factories.group.create(add_another=True, name="Test group", form__title="Test form")
        question = factories.question.create(form=group.form, parent=group, name="Test question")

        factories.submission.create(
            collection=group.form.collection,
            mode=SubmissionModeEnum.TEST,
            data={
                f"{str(group.id)}": [
                    {str(question.id): "first"},
                    {str(question.id): "second"},
                    {str(question.id): "third"},
                ]
            },
        )
        factories.submission.create(
            collection=group.form.collection,
            mode=SubmissionModeEnum.TEST,
            data={f"{str(group.id)}": [{str(question.id): "only first"}]},
        )

        c_helper = CollectionHelper(collection=group.form.collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.DictReader(StringIO(csv_content))

        rows = list(reader)
        assert rows[0]["[Test form] [Test group] Test question (1)"] == "first"
        assert rows[0]["[Test form] [Test group] Test question (2)"] == "second"
        assert rows[0]["[Test form] [Test group] Test question (3)"] == "third"

        assert rows[1]["[Test form] [Test group] Test question (1)"] == "only first"
        assert rows[1]["[Test form] [Test group] Test question (2)"] == "NOT_ASKED"
        assert rows[1]["[Test form] [Test group] Test question (3)"] == "NOT_ASKED"

    def test_generate_json_content_for_all_submissions_all_question_types_appear_correctly(self, factories):
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
                    "certified_by": None,
                    "certified_at_utc": mock.ANY,
                    "grant_recipient": mock.ANY,
                    "reference": mock.ANY,
                    "status": "In progress",
                    "submitted_at_utc": None,
                    "sections": [
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

    def test_generate_json_content_for_all_submissions_all_question_types_appear_correctly_live(
        self, factories, db_session
    ):
        factories.data_source_item.reset_sequence()
        user = factories.user.create(email="certifier@test.com")
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__live=1,
            create_completed_submissions_each_question_type__use_random_data=False,
        )
        factories.submission_event.create(
            submission=collection.live_submissions[0],
            event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
            created_by=user,
            created_at_utc=datetime(2025, 12, 1, 0, 0, 0),
        )
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.LIVE)
        json_data = c_helper.generate_json_content_for_all_submissions()
        submissions = json.loads(json_data)

        assert submissions == {
            "submissions": [
                {
                    "created_at_utc": mock.ANY,
                    "created_by": mock.ANY,
                    "certified_by": "certifier@test.com",
                    "certified_at_utc": "12am on Monday 1 December 2025",
                    "grant_recipient": AnyStringMatching(r"Organisation \d+"),
                    "reference": mock.ANY,
                    "status": "In progress",
                    "submitted_at_utc": None,
                    "sections": [
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

    def test_generate_json_content_for_all_submissions_add_another_lists(self, factories):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        json_data = c_helper.generate_json_content_for_all_submissions()
        submissions = json.loads(json_data)

        assert submissions == {
            "submissions": [
                {
                    "created_at_utc": mock.ANY,
                    "created_by": mock.ANY,
                    "certified_by": None,
                    "certified_at_utc": mock.ANY,
                    "grant_recipient": mock.ANY,
                    "reference": mock.ANY,
                    "status": "In progress",
                    "submitted_at_utc": None,
                    "sections": [
                        {
                            "answers": {
                                "Your name": "test name",
                                "Organisation name": "test org name",
                                "organisation contacts test group": [
                                    {"Contact name": "test name 0", "Contact email": "test_user_0@email.com"},
                                    {"Contact name": "test name 1", "Contact email": "test_user_1@email.com"},
                                    {"Contact name": "test name 2", "Contact email": "test_user_2@email.com"},
                                    {"Contact name": "test name 3", "Contact email": "test_user_3@email.com"},
                                    {"Contact name": "test name 4", "Contact email": "test_user_4@email.com"},
                                ],
                                "Length of service": {"value": 3},
                            },
                            "name": "Add another nested group test form",
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


class TestSubmissionValidation:
    def test_submit_fails_when_answer_no_longer_valid(self, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, order=1)

        add_question_validation(
            q2,
            user,
            GreaterThan(
                question_id=q2.id,
                collection_id=q2.form.collection_id,
                minimum_value=None,
                minimum_expression=f"(({q1.safe_qid}))",
            ),
        )

        submission = factories.submission.create(collection=form.collection)

        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 100}}

        helper = SubmissionHelper(submission)
        helper.toggle_form_completed(form, user, True)

        submission.data[str(q1.id)] = {"value": 150}
        helper.cached_get_answer_for_question.cache_clear()
        helper.cached_evaluation_context = ExpressionContext.build_expression_context(
            collection=submission.collection, submission_helper=helper, mode="evaluation"
        )

        with pytest.raises(ValueError) as e:
            helper.submit(user)

        assert "no longer valid" in str(e.value)

    def test_submit_succeeds_when_all_answers_valid(self, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, order=1)

        add_question_validation(
            q2,
            user,
            GreaterThan(
                question_id=q2.id,
                collection_id=q2.form.collection_id,
                minimum_value=None,
                minimum_expression=f"(({q1.safe_qid}))",
            ),
        )

        submission = factories.submission.create(collection=form.collection, mode=SubmissionModeEnum.TEST)

        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 100}}

        helper = SubmissionHelper(submission)
        helper.toggle_form_completed(form, user, True)

        helper.submit(user)

        assert helper.is_submitted

    def test_certification_fails_when_answer_no_longer_valid(self, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.create(form=form, data_type=QuestionDataType.INTEGER, order=1)

        add_question_validation(
            q2,
            user,
            GreaterThan(
                question_id=q2.id,
                collection_id=q2.form.collection_id,
                minimum_value=None,
                minimum_expression=f"(({q1.safe_qid}))",
            ),
        )

        collection = form.collection
        collection.requires_certification = True

        submission = factories.submission.create(collection=collection)

        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 100}}

        helper = SubmissionHelper(submission)
        helper.toggle_form_completed(form, user, True)

        submission.data[str(q1.id)] = {"value": 150}
        helper.cached_get_answer_for_question.cache_clear()
        helper.cached_evaluation_context = ExpressionContext.build_expression_context(
            collection=submission.collection, submission_helper=helper, mode="evaluation"
        )

        with pytest.raises(ValueError) as e:
            helper.mark_as_sent_for_certification(user)

        assert "no longer valid" in str(e.value)
