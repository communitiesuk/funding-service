import csv
import json
import uuid
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest

from app.common.collections.forms import build_question_form
from app.common.collections.types import (
    NOT_ASKED,
    DateAnswer,
    DecimalAnswer,
    FileUploadAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    YesNoAnswer,
)
from app.common.data import interfaces
from app.common.data.models import Expression
from app.common.data.types import (
    CollectionStatusEnum,
    ExpressionType,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistSectionStatusEnum,
)
from app.common.exceptions import SubmissionAnswerConflict
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import GreaterThan, IsYes
from app.common.expressions.references import ExpressionReference
from app.common.helpers.collections import (
    AllSubmissionsHelper,
    CollectionIsNotOpenError,
    SubmissionAuthorisationError,
    SubmissionHelper,
    SubmissionIsNotSubmittedError,
)
from app.common.helpers.submission_events import SubmissionEventHelper
from tests.models import FactoryAnswer
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
            helper.submit_answer_for_question(question.id, form, submission.created_by)

            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("User submitted data")

        def test_get_data_maps_type(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.NUMBER,
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
            )
            question_2 = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"),
                data_type=QuestionDataType.NUMBER,
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL),
                form=question.form,
            )
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294=5
            )
            helper.submit_answer_for_question(question.id, form, submission.created_by)
            form = build_question_form([question_2], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994295=Decimal("7.6")
            )
            helper.submit_answer_for_question(question_2.id, form, submission.created_by)

            assert helper.cached_get_answer_for_question(question.id) == IntegerAnswer(value=5)
            assert helper.cached_get_answer_for_question(question_2.id) == DecimalAnswer(value=Decimal("7.6"))

        def test_can_get_falsey_answers(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.NUMBER
            )
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294=0
            )
            helper.submit_answer_for_question(question.id, form, submission.created_by)

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
                helper.submit_answer_for_question(
                    submission_submitted.collection.forms[0].cached_questions[0].id,
                    form,
                    submission_submitted.created_by,
                )

            assert str(e.value) == AnyStringMatching(
                "Could not submit answer for question_id=[a-z0-9-]+ "
                "because the answers are locked for submission id=[a-z0-9-]+."
            )

        def test_cannot_submit_answer_when_collection_closed(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                form__collection__status=CollectionStatusEnum.CLOSED,
            )
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="User submitted data"
            )

            with pytest.raises(ValueError, match="answers are locked"):
                helper.submit_answer_for_question(question.id, form, submission.created_by)

        def test_submit_duplicate_submission_name_raises_conflict(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
            )
            collection = question.form.collection
            collection.submission_name_question_id = question.id
            db_session.flush()

            grant_recipient = factories.grant_recipient.create(grant=collection.grant)
            factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha"))],
            )
            new_submission = factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
            )
            helper = SubmissionHelper(new_submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Alpha"
            )

            with pytest.raises(SubmissionAnswerConflict, match="already exists"):
                helper.submit_answer_for_question(question.id, form, new_submission.created_by)

        def test_submit_duplicate_submission_name_is_case_insensitive(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
            )
            collection = question.form.collection
            collection.submission_name_question_id = question.id
            db_session.flush()

            grant_recipient = factories.grant_recipient.create(grant=collection.grant)
            factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha"))],
            )
            new_submission = factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
            )
            helper = SubmissionHelper(new_submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="alpha"
            )

            with pytest.raises(SubmissionAnswerConflict, match="already exists"):
                helper.submit_answer_for_question(question.id, form, new_submission.created_by)

        def test_submit_unique_submission_name_succeeds(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
            )
            collection = question.form.collection
            collection.submission_name_question_id = question.id
            db_session.flush()

            grant_recipient = factories.grant_recipient.create(grant=collection.grant)
            factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha"))],
            )
            new_submission = factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
            )
            helper = SubmissionHelper(new_submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Beta"
            )

            helper.submit_answer_for_question(question.id, form, new_submission.created_by)
            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("Beta")

        def test_submit_same_name_on_own_submission_succeeds(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
            )
            collection = question.form.collection
            collection.submission_name_question_id = question.id
            db_session.flush()

            grant_recipient = factories.grant_recipient.create(grant=collection.grant)
            submission = factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha"))],
            )
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Alpha"
            )

            helper.submit_answer_for_question(question.id, form, submission.created_by)
            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("Alpha")

        def test_submit_duplicate_name_skipped_for_preview_submission(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
            )
            collection = question.form.collection
            collection.submission_name_question_id = question.id
            db_session.flush()

            grant_recipient = factories.grant_recipient.create(grant=collection.grant)
            factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha"))],
            )
            preview_submission = factories.submission.create(
                collection=collection,
                grant_recipient=None,
                mode=SubmissionModeEnum.PREVIEW,
            )
            helper = SubmissionHelper(preview_submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Alpha"
            )

            helper.submit_answer_for_question(question.id, form, preview_submission.created_by)
            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("Alpha")

        def test_submit_changed_answer_raises_for_managed_submission_name(self, db_session, factories):
            question = factories.question.create(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"),
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
                form__collection__multiple_submissions_are_managed_by_service=True,
            )
            collection = question.form.collection
            collection.submission_name_question_id = question.id
            db_session.flush()

            grant_recipient = factories.grant_recipient.create(grant=collection.grant)
            submission = factories.submission.create(
                collection=collection,
                grant_recipient=grant_recipient,
                mode=SubmissionModeEnum.LIVE,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha"))],
            )
            helper = SubmissionHelper(submission)

            form = build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Beta"
            )

            with pytest.raises(RuntimeError, match="cannot be changed"):
                helper.submit_answer_for_question(question.id, form, submission.created_by)

            assert helper.cached_get_answer_for_question(question.id) == TextSingleLineAnswer("Alpha")

    class TestRemoveEntryForAddAnother:
        def test_remove_entry_for_add_another(self, db_session, factories):
            collection = factories.collection.create(
                create_completed_submissions_add_another_nested_group__test=1,
                create_completed_submissions_add_another_nested_group__use_random_data=False,
                create_completed_submissions_add_another_nested_group__number_of_add_another_answers=2,
            )
            questions = collection.forms[0].cached_questions
            helper = SubmissionHelper(collection.test_submissions[0])

            add_another_container = questions[2].add_another_container

            assert helper.submission.data_manager.get_count_for_add_another(add_another_container) == 2

            helper.remove_entry_for_add_another(add_another_container, 0)

            assert helper.submission.data_manager.get_count_for_add_another(add_another_container) == 1

        def test_remove_entry_for_add_another_clears_file_uploads(self, db_session, factories, mock_s3_service_calls):

            add_another_container = factories.group.create(add_another=True)
            file_upload = factories.question.create(
                form=add_another_container.form,
                data_type=QuestionDataType.FILE_UPLOAD,
                parent=add_another_container,
            )
            submission = factories.submission.create(
                collection=add_another_container.form.collection,
            )
            for i in range(2):
                submission.data_manager.set(
                    file_upload,
                    FileUploadAnswer(
                        filename="test-document.pdf",
                        size=0,
                        mime_type="application/pdf",
                        key=f"an-s3-key-{i}",
                    ),
                    add_another_index=i,
                )

            helper = SubmissionHelper(submission)

            assert helper.submission.data_manager.get_count_for_add_another(add_another_container) == 2

            helper.remove_entry_for_add_another(add_another_container, 0)

            assert helper.submission.data_manager.get_count_for_add_another(add_another_container) == 1

            assert len(mock_s3_service_calls.delete_file_calls) == 1
            assert mock_s3_service_calls.delete_file_calls[0].args[0] == "an-s3-key-0"

    class TestRemoveAnswerForQuestion:
        def test_remove_answer_for_file_upload_question_and_clears_cache(
            self, db_session, factories, mock_s3_service_calls
        ):
            question = factories.question.create(data_type=QuestionDataType.FILE_UPLOAD)
            submission = factories.submission.create(
                collection=question.form.collection,
                answers=[
                    FactoryAnswer(
                        question,
                        FileUploadAnswer(
                            filename="test-document.pdf",
                            size=0,
                            mime_type="application/pdf",
                            key="an-s3-key",
                        ),
                    )
                ],
            )
            helper = SubmissionHelper(submission)

            assert helper.cached_get_answer_for_question(question.id) == FileUploadAnswer(
                filename="test-document.pdf",
                size=0,
                mime_type="application/pdf",
                scanned_for_viruses=False,
                key="an-s3-key",
            )

            helper.remove_answer_for_question(question.id)

            assert helper.cached_get_answer_for_question(question.id) is None
            assert len(mock_s3_service_calls.delete_file_calls) == 1
            assert mock_s3_service_calls.delete_file_calls[0].args[0] == "an-s3-key"

        def test_cannot_remove_answer_on_submitted_submission(self, db_session, factories, submission_submitted):
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED

            question = submission_submitted.collection.forms[0].cached_questions[0]

            with pytest.raises(ValueError) as e:
                helper.remove_answer_for_question(question.id)

            assert str(e.value) == AnyStringMatching(
                "Could not remove answer for question_id=[a-z0-9-]+ "
                "because the answers are locked for submission id=[a-z0-9-]+."
            )

        def test_cannot_remove_answer_when_collection_closed(self, db_session, factories):
            question = factories.question.create(form__collection__status=CollectionStatusEnum.CLOSED)
            submission = factories.submission.create(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("some answer"))],
            )
            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError, match="answers are locked"):
                helper.remove_answer_for_question(question.id)

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
            assert len(QuestionDataType) == 10, "Update this test if adding new questions"

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
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"),
                data_type=QuestionDataType.NUMBER,
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
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
            q10 = factories.question.create(
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429d"),
                data_type=QuestionDataType.NUMBER,
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL),
            )
            q11 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429e"),
                data_type=QuestionDataType.FILE_UPLOAD,
            )

            submission = factories.submission.create(
                collection=form.collection,
                answers=[
                    FactoryAnswer(q1, TextSingleLineAnswer("answer")),
                    FactoryAnswer(q2, TextMultiLineAnswer("answer\nthis")),
                    FactoryAnswer(q3, IntegerAnswer(value=50)),
                    FactoryAnswer(q4, YesNoAnswer(True)),
                    FactoryAnswer(q5, SingleChoiceFromListAnswer(key="my-key", label="My label")),
                    FactoryAnswer(q6, TextSingleLineAnswer("name@example.com")),
                    FactoryAnswer(q7, TextSingleLineAnswer("https://example.com")),
                    FactoryAnswer(
                        q8,
                        MultipleChoiceFromListAnswer(
                            choices=[{"key": "cheddar", "label": "Cheddar"}, {"key": "stilton", "label": "Stilton"}]
                        ),
                    ),
                    FactoryAnswer(q9, DateAnswer(answer=date(2003, 2, 1))),
                    FactoryAnswer(q10, DecimalAnswer(value=Decimal(12.21))),
                    FactoryAnswer(
                        q11,
                        FileUploadAnswer(filename="test-document.pdf", size=0, mime_type="application/pdf"),
                    ),
                ],
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
                "q_d696aebc49d24170a92fb6ef4299429d": 12.21,
                "q_d696aebc49d24170a92fb6ef4299429e": "test-document.pdf",
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

            assert helper.cached_evaluation_context == ExpressionContext()

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 10, "Update this test if adding new questions"

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
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"),
                data_type=QuestionDataType.NUMBER,
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
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
            q10 = factories.question.create(
                form=form_two,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429d"),
                data_type=QuestionDataType.NUMBER,
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL),
            )
            q11 = factories.question.create(
                form=form,
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef4299429e"),
                data_type=QuestionDataType.FILE_UPLOAD,
            )

            submission = factories.submission.create(
                collection=form.collection,
                answers=[
                    FactoryAnswer(q1, TextSingleLineAnswer("answer")),
                    FactoryAnswer(q2, TextMultiLineAnswer("answer\nthis")),
                    FactoryAnswer(q3, IntegerAnswer(value=50)),
                    FactoryAnswer(q4, YesNoAnswer(True)),
                    FactoryAnswer(q5, SingleChoiceFromListAnswer(key="my-key", label="My label")),
                    FactoryAnswer(q6, TextSingleLineAnswer("name@example.com")),
                    FactoryAnswer(q7, TextSingleLineAnswer("https://example.com")),
                    FactoryAnswer(
                        q8,
                        MultipleChoiceFromListAnswer(
                            choices=[{"key": "cheddar", "label": "Cheddar"}, {"key": "stilton", "label": "Stilton"}]
                        ),
                    ),
                    FactoryAnswer(q9, DateAnswer(answer=date(2000, 1, 1))),
                    FactoryAnswer(q10, DecimalAnswer(value=Decimal(12.21))),
                    FactoryAnswer(
                        q11,
                        FileUploadAnswer(filename="test-document.pdf", size=0, mime_type="application/pdf"),
                    ),
                ],
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
                    "q_d696aebc49d24170a92fb6ef4299429d": 12.21,
                    "q_d696aebc49d24170a92fb6ef4299429e": "test-document.pdf",
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
                submission.created_by,
            )

            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form([question_two], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994295="User submitted data"
                ),
                submission.created_by,
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
                submission.created_by,
            )
            assert helper.get_status_for_form(form_two) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form_two) == TasklistSectionStatusEnum.IN_PROGRESS

        def test_form_status_with_no_questions(self, db_session, factories):
            form = factories.form.create()
            submission = factories.submission.create(collection=form.collection)
            helper = SubmissionHelper(submission)
            assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.NOT_NEEDED
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
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
                submission.created_by,
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form([question_two], evaluation_context=EC(), interpolation_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994295="User submitted data"
                ),
                submission.created_by,
            )
            helper.toggle_form_completed(question_two.form, submission.created_by, True)

            assert helper.get_status_for_form(question_two.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question_two.form) == TasklistSectionStatusEnum.COMPLETED

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.mark_as_sent_for_certification(submission.created_by)

            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
            assert helper.events.submission_state.is_awaiting_sign_off is True
            assert helper.events.submission_state.sent_for_certification_by is submission.created_by

            helper.decline_certification(certifier, "Reason for declining")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.IN_PROGRESS
            assert helper.events.submission_state.sent_for_certification_by is submission.created_by
            assert helper.events.submission_state.is_awaiting_sign_off is False
            assert helper.events.submission_state.declined_by == certifier
            assert helper.events.submission_state.declined_reason == "Reason for declining"

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper.get_status_for_form(question_two.form) == TasklistSectionStatusEnum.IN_PROGRESS

            helper.toggle_form_completed(question.form, submission.created_by, True)
            helper.toggle_form_completed(question_two.form, submission.created_by, True)

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.mark_as_sent_for_certification(submission.created_by)

            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            helper.certify(certifier)

            assert helper.events.submission_state.is_awaiting_sign_off is False
            assert helper.events.submission_state.is_approved is True
            assert helper.events.submission_state.certified_by == certifier

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.submit(certifier)

            assert helper.status == SubmissionStatusEnum.SUBMITTED
            # TODO: remove redundant status check after full migration to DB submission.status
            assert helper.submission.status == SubmissionStatusEnum.SUBMITTED
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
                submission.created_by,
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
                submission.created_by,
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
                submission.created_by,
            )

            with pytest.raises(ValueError) as e:
                helper.submit(submission.created_by)

            assert str(e.value) == AnyStringMatching(
                r"Could not submit submission id=[a-z0-9-]+ because not all forms are complete."
            )

        def test_in_immutable_state_when_collection_closed(self, db_session, factories):
            question = factories.question.create(form__collection__status=CollectionStatusEnum.CLOSED)
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.in_immutable_state is True

        def test_not_in_immutable_state_when_collection_open(self, db_session, factories):
            question = factories.question.create(form__collection__status=CollectionStatusEnum.OPEN)
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.in_immutable_state is False

        def test_in_answers_locked_state_when_collection_closed(self, db_session, factories):
            question = factories.question.create(form__collection__status=CollectionStatusEnum.CLOSED)
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.in_answers_locked_state is True

        def test_cannot_toggle_form_completed_when_collection_closed(self, db_session, factories):
            question = factories.question.create(form__collection__status=CollectionStatusEnum.CLOSED)
            submission = factories.submission.create(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("some answer"))],
            )
            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError, match="answers are locked"):
                helper.toggle_form_completed(question.form, submission.created_by, True)

        def test_status_is_not_submitted_when_collection_closed(self, db_session, factories):
            question = factories.question.create(form__collection__status=CollectionStatusEnum.CLOSED)
            submission = factories.submission.create(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("some answer"))],
            )
            helper = SubmissionHelper(submission)

            assert helper.status == SubmissionStatusEnum.NOT_SUBMITTED

        def test_status_is_submitted_when_collection_closed_and_already_submitted(
            self, db_session, factories, submission_submitted
        ):
            submission_submitted.collection.status = CollectionStatusEnum.CLOSED
            helper = SubmissionHelper(submission_submitted)

            assert helper.status == SubmissionStatusEnum.SUBMITTED

        def test_submission_status_with_not_needed_forms(self, db_session, factories, mock_notification_service_calls):
            org = factories.organisation.create()
            grant = factories.grant.create()
            gr = factories.grant_recipient.create(organisation=org, grant=grant)
            collection = factories.collection.create(
                grant=grant,
                reporting_period_start_date=date(2025, 1, 1),
                reporting_period_end_date=date(2025, 3, 31),
                requires_certification=False,
            )

            question = factories.question.create(form__collection=collection, data_type=QuestionDataType.YES_NO)
            form_two = factories.form.create(collection=collection)
            factories.question.create(
                form=form_two,
                expressions=[
                    Expression.from_evaluatable_expression(
                        IsYes(subject_reference=ExpressionReference.from_question(question)),
                        ExpressionType.CONDITION,
                        collection.created_by,
                    )
                ],
            )

            form_three = factories.form.create(collection=collection)
            question_three = factories.question.create(form=form_three)

            submission = factories.submission.create(
                collection=question.form.collection,
                grant_recipient=gr,
                answers=[
                    FactoryAnswer(question, YesNoAnswer(False)),
                    FactoryAnswer(question_three, TextSingleLineAnswer("Hello")),
                ],
            )

            helper = SubmissionHelper(submission)
            helper.toggle_form_completed(question.form, submission.created_by, True)
            helper.toggle_form_completed(form_three, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.get_status_for_form(form_two) == TasklistSectionStatusEnum.NOT_NEEDED
            assert helper.get_status_for_form(form_three) == TasklistSectionStatusEnum.COMPLETED

            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

            helper.submit(submission.created_by)

            assert helper.status == SubmissionStatusEnum.SUBMITTED

        def test_changes_made_and_submitted_with_changes_statuses(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("original"))],
            )
            previous_data = deepcopy(submission.data_manager.data)
            submission.data_manager.set(question, TextSingleLineAnswer("updated"))

            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                    related_entity_id=question.form.id,
                ),
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                ),
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                ),
            ]

            helper = SubmissionHelper(submission)

            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.CHANGES_MADE
            assert helper._calculate_submission_status() == SubmissionStatusEnum.SUBMITTED_WITH_CHANGES

    class TestIgnoredFormsForSubmissionStatus:
        @staticmethod
        def _managed_collection(factories, db_session, extra_name_form_questions=0):
            name_question = factories.question.create(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
                form__collection__multiple_submissions_are_managed_by_service=True,
            )
            collection = name_question.form.collection
            collection.submission_name_question_id = name_question.id
            extra_name_questions = [
                factories.question.create(form=name_question.form, data_type=QuestionDataType.TEXT_SINGLE_LINE)
                for _ in range(extra_name_form_questions)
            ]
            other_form = factories.form.create(collection=collection)
            other_question = factories.question.create(form=other_form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

            return collection, name_question, extra_name_questions, other_question

        @staticmethod
        def _answer(helper, question, value, user):
            helper.submit_answer_for_question(
                question.id,
                build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                    **{question.safe_qid: value}
                ),
                user,
            )

        @classmethod
        def _complete_form(cls, helper, form, questions, user):
            for question in questions:
                cls._answer(helper, question, "answer", user)
            helper.toggle_form_completed(form, user, True)

        def test_completed_name_only_form_is_treated_as_not_started(self, db_session, factories):
            collection, name_question, _, other_question = self._managed_collection(factories, db_session)
            submission = factories.submission.create(collection=collection)
            helper = SubmissionHelper(submission)

            assert helper.form_is_managed_by_service(name_question.form) is True
            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            self._complete_form(helper, name_question.form, [name_question], submission.created_by)

            assert helper.get_status_for_form(name_question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            self._answer(helper, other_question, "data", submission.created_by)

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

        def test_name_form_with_additional_questions_counts_towards_status(self, db_session, factories):
            collection, name_question, extra_name_questions, other_question = self._managed_collection(
                factories, db_session, extra_name_form_questions=1
            )
            submission = factories.submission.create(collection=collection)
            helper = SubmissionHelper(submission)

            assert helper.form_is_managed_by_service(name_question.form) is False
            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            self._complete_form(
                helper, name_question.form, [name_question, *extra_name_questions], submission.created_by
            )

            assert helper.get_status_for_form(name_question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            self._complete_form(helper, other_question.form, [other_question], submission.created_by)

            assert helper.get_status_for_form(other_question.form) == TasklistSectionStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

        def test_name_form_counts_when_not_managed_by_service(self, db_session, factories):
            name_question = factories.question.create(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
                form__collection__multiple_submissions_are_managed_by_service=False,
            )
            collection = name_question.form.collection
            collection.submission_name_question_id = name_question.id
            factories.question.create(form__collection=collection, data_type=QuestionDataType.TEXT_SINGLE_LINE)
            db_session.flush()
            submission = factories.submission.create(collection=collection)
            helper = SubmissionHelper(submission)

            assert helper.form_is_managed_by_service(name_question.form) is False
            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            self._complete_form(helper, name_question.form, [name_question], submission.created_by)

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

        def test_single_submission_collection_ignores_nothing(self, db_session, factories):
            question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
            submission = factories.submission.create(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.form_is_managed_by_service(question.form) is False
            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            self._answer(helper, question, "data", submission.created_by)

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

        def test_raises_when_managed_multi_submission_has_no_name_question(self, db_session, factories):
            question = factories.question.create(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                form__collection__allow_multiple_submissions=True,
                form__collection__multiple_submissions_are_managed_by_service=False,
            )
            collection = question.form.collection
            submission = factories.submission.create(collection=collection)
            collection.multiple_submissions_are_managed_by_service = True
            db_session.flush()
            helper = SubmissionHelper(submission)

            with pytest.raises(RuntimeError, match="Submission name question is required for multiple submissions"):
                helper.form_is_managed_by_service(question.form)

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

    class TestGetStatus:
        def test_returns_not_started_when_no_submission_and_open(self, db_session, factories):
            collection = factories.collection.create(status=CollectionStatusEnum.OPEN)
            factories.form.create(collection=collection)

            assert SubmissionHelper.get_status(None, collection) == SubmissionStatusEnum.NOT_STARTED

        def test_returns_not_submitted_when_no_submission_and_closed(self, db_session, factories):
            collection = factories.collection.create(status=CollectionStatusEnum.CLOSED)
            factories.form.create(collection=collection)

            assert SubmissionHelper.get_status(None, collection) == SubmissionStatusEnum.NOT_SUBMITTED

        def test_returns_submission_status_when_submission_exists(self, db_session, factories, submission_in_progress):
            assert (
                SubmissionHelper.get_status(submission_in_progress, submission_in_progress.collection)
                == SubmissionStatusEnum.IN_PROGRESS
            )

        def test_raises_when_submission_does_not_belong_to_collection(self, db_session, factories):
            collection_a = factories.collection.create()
            collection_b = factories.collection.create()
            factories.form.create(collection=collection_a)
            submission = factories.submission.create(collection=collection_a)

            with pytest.raises(ValueError, match="does not belong"):
                SubmissionHelper.get_status(submission, collection_b)

    class TestGetAccessSubmissionAction:
        def test_start_report_when_no_submission_and_open(self, db_session, factories):
            grant_recipient = factories.grant_recipient.create()
            collection = factories.collection.create(grant=grant_recipient.grant, status=CollectionStatusEnum.OPEN)
            factories.form.create(collection=collection)

            result = SubmissionHelper.get_access_submission_action(collection, grant_recipient, None)

            assert result["label"] == "Start report"
            assert result["href"]

        def test_did_not_start_when_no_submission_and_closed(self, db_session, factories):
            grant_recipient = factories.grant_recipient.create()
            collection = factories.collection.create(grant=grant_recipient.grant, status=CollectionStatusEnum.CLOSED)
            factories.form.create(collection=collection)

            result = SubmissionHelper.get_access_submission_action(collection, grant_recipient, None)

            assert result["label"] == "Did not start"
            assert result["href"] is None

        def test_view_report_when_collection_closed_with_submission(self, db_session, factories):
            grant_recipient = factories.grant_recipient.create()
            question = factories.question.create(
                form__collection__grant=grant_recipient.grant,
                form__collection__status=CollectionStatusEnum.CLOSED,
            )
            submission = factories.submission.create(
                collection=question.form.collection, grant_recipient=grant_recipient
            )

            result = SubmissionHelper.get_access_submission_action(
                question.form.collection, grant_recipient, submission
            )

            assert result["label"] == "View report"
            assert result["href"]

        def test_continue_report_when_in_progress(self, db_session, factories, submission_in_progress, grant_recipient):
            result = SubmissionHelper.get_access_submission_action(
                submission_in_progress.collection, grant_recipient, submission_in_progress
            )

            assert result["label"] == "Continue report"
            assert result["href"]

        def test_continue_report_when_has_change_requests(self, submission_changes_requested, grant_recipient):
            result = SubmissionHelper.get_access_submission_action(
                submission_changes_requested.collection, grant_recipient, submission_changes_requested
            )

            assert result["label"] == "Continue report"
            assert result["href"]

        def test_start_report_when_not_started(self, db_session, factories):
            grant_recipient = factories.grant_recipient.create()
            question = factories.question.create(
                form__collection__grant=grant_recipient.grant,
                form__collection__status=CollectionStatusEnum.OPEN,
            )
            submission = factories.submission.create(
                collection=question.form.collection, grant_recipient=grant_recipient
            )

            result = SubmissionHelper.get_access_submission_action(
                question.form.collection, grant_recipient, submission
            )

            assert result["label"] == "Start report"
            assert result["href"]

        def test_view_report_when_submitted(self, db_session, factories, submission_submitted, grant_recipient):
            result = SubmissionHelper.get_access_submission_action(
                submission_submitted.collection, grant_recipient, submission_submitted
            )

            assert result["label"] == "View report"
            assert result["href"]

        def test_raises_when_submission_does_not_belong_to_collection(self, db_session, factories):
            grant_recipient = factories.grant_recipient.create()
            collection_a = factories.collection.create(grant=grant_recipient.grant)
            collection_b = factories.collection.create(grant=grant_recipient.grant)
            factories.form.create(collection=collection_a)
            submission = factories.submission.create(collection=collection_a, grant_recipient=grant_recipient)

            with pytest.raises(ValueError, match="does not belong"):
                SubmissionHelper.get_access_submission_action(collection_b, grant_recipient, submission)

    class TestGetAnswerForQuestion:
        def test_get_answer_for_question(self, factories):
            question = factories.question.create()
            submission = factories.submission.create(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("test name"))],
            )
            helper = SubmissionHelper(submission)
            answer = helper._get_answer_for_question(question.id)
            assert answer == TextSingleLineAnswer("test name")

        def test_get_answer_for_question_not_answered(self, factories, mocker):
            question = factories.question.create()
            submission = factories.submission.create(collection=question.form.collection)

            helper = SubmissionHelper(submission)
            answer = helper._get_answer_for_question(question.id)

            assert answer is None

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

            helper.certify(certifier_user)

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

            helper.certify(certifier_user)

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

            helper.certify(certifier_user)
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

        @pytest.mark.parametrize(
            "submission_mode, expected_email_recipients",
            (
                (SubmissionModeEnum.PREVIEW, 0),
                (SubmissionModeEnum.TEST, 1),
                (SubmissionModeEnum.LIVE, 2),
            ),
        )
        def test_sends_emails_to_users_based_on_submission_mode(
            self,
            factories,
            submission_ready_to_submit,
            mock_notification_service_calls,
            data_provider_user,
            submission_mode,
            expected_email_recipients,
        ):
            factories.user_role.create(
                organisation=submission_ready_to_submit.grant_recipient.organisation,
                grant=submission_ready_to_submit.grant_recipient.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )

            submission_ready_to_submit.mode = submission_mode
            submission_ready_to_submit.collection.requires_certification = False
            helper = SubmissionHelper(submission_ready_to_submit)

            helper.submit(user=data_provider_user)

            assert helper.status == SubmissionStatusEnum.SUBMITTED
            assert len(mock_notification_service_calls) == expected_email_recipients

        def test_submit_when_collection_closed(
            self, factories, submission_ready_to_submit, data_provider_user, mock_notification_service_calls
        ):
            submission_ready_to_submit.collection.requires_certification = False
            submission_ready_to_submit.collection.status = CollectionStatusEnum.CLOSED
            helper = SubmissionHelper(submission_ready_to_submit)

            with pytest.raises(ValueError, match="as it is in an immutable state"):
                helper.submit(data_provider_user)

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

        @pytest.mark.parametrize(
            "submission_mode, expected_data_provider_emails, expected_certifier_emails",
            (
                (SubmissionModeEnum.PREVIEW, 0, 0),
                (SubmissionModeEnum.TEST, 1, 1),
                (SubmissionModeEnum.LIVE, 2, 2),
            ),
        )
        def test_sends_emails_to_users_based_on_submission_mode(
            self,
            app,
            factories,
            submission_ready_to_submit,
            mock_notification_service_calls,
            data_provider_user,
            submission_mode,
            expected_data_provider_emails,
            expected_certifier_emails,
            user,
        ):
            _data_provider_2 = factories.user_role.create(
                organisation=submission_ready_to_submit.grant_recipient.organisation,
                grant=submission_ready_to_submit.grant_recipient.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )
            _certifier_1 = factories.user_role.create(
                organisation=submission_ready_to_submit.grant_recipient.organisation,
                grant=submission_ready_to_submit.grant_recipient.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )
            _certifier_2 = factories.user_role.create(
                organisation=submission_ready_to_submit.grant_recipient.organisation,
                grant=submission_ready_to_submit.grant_recipient.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )

            submission_ready_to_submit.mode = submission_mode
            helper = SubmissionHelper(submission_ready_to_submit)

            helper.mark_as_sent_for_certification(user=data_provider_user)
            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            data_provider_emails = [
                call
                for call in mock_notification_service_calls
                if (
                    call.args[1]
                    == app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_SENT_FOR_CERTIFICATION_CONFIRMATION_TEMPLATE_ID"]
                )
            ]
            certifier_emails = [
                call
                for call in mock_notification_service_calls
                if (call.args[1] == app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_READY_TO_CERTIFY_TEMPLATE_ID"])
            ]

            assert len(data_provider_emails) == expected_data_provider_emails
            assert len(certifier_emails) == expected_certifier_emails

        def test_mark_as_sent_for_certification_when_collection_closed(
            self, factories, submission_ready_to_submit, data_provider_user, mock_notification_service_calls
        ):
            submission_ready_to_submit.collection.status = CollectionStatusEnum.CLOSED
            helper = SubmissionHelper(submission_ready_to_submit)

            with pytest.raises(ValueError, match="answers-locked state"):
                helper.mark_as_sent_for_certification(data_provider_user)

            assert len(mock_notification_service_calls) == 0

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

        def test_certify_when_collection_closed(
            self, factories, submission_awaiting_sign_off, certifier_user, mock_notification_service_calls
        ):
            submission_awaiting_sign_off.collection.status = CollectionStatusEnum.CLOSED
            helper = SubmissionHelper(submission_awaiting_sign_off)

            with pytest.raises(ValueError, match="immutable state"):
                helper.certify(certifier_user)

    class TestCertificationDeclined:
        def test_decline(
            self, data_provider_user, certifier_user, submission_awaiting_sign_off, mock_notification_service_calls
        ) -> None:
            helper = SubmissionHelper(submission_awaiting_sign_off)
            assert helper.collection.requires_certification is True
            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            helper.decline_certification(user=certifier_user, declined_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            assert len(mock_notification_service_calls) == 2

        @pytest.mark.parametrize(
            "submission_mode, expected_data_provider_emails, expected_certifier_emails",
            (
                (SubmissionModeEnum.PREVIEW, 0, 0),
                (SubmissionModeEnum.TEST, 1, 1),
                (SubmissionModeEnum.LIVE, 2, 2),
            ),
        )
        def test_sends_emails_to_users_based_on_submission_mode(
            self,
            app,
            factories,
            submission_awaiting_sign_off,
            mock_notification_service_calls,
            submission_mode,
            expected_data_provider_emails,
            expected_certifier_emails,
            data_provider_user,
            certifier_user,
            user,
        ):
            _data_provider_2 = factories.user_role.create(
                organisation=submission_awaiting_sign_off.grant_recipient.organisation,
                grant=submission_awaiting_sign_off.grant_recipient.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )
            _certifier_2 = factories.user_role.create(
                organisation=submission_awaiting_sign_off.grant_recipient.organisation,
                grant=submission_awaiting_sign_off.grant_recipient.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )

            submission_awaiting_sign_off.mode = submission_mode
            helper = SubmissionHelper(submission_awaiting_sign_off)

            helper.decline_certification(user=certifier_user, declined_reason="Test reason")
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            data_provider_emails = [
                call
                for call in mock_notification_service_calls
                if (
                    call.kwargs["template_id"]
                    == app.config["GOVUK_NOTIFY_ACCESS_SUBMITTER_REPORT_DECLINED_TEMPLATE_ID"]
                )
            ]
            certifier_emails = [
                call
                for call in mock_notification_service_calls
                if (
                    call.kwargs["template_id"]
                    == app.config["GOVUK_NOTIFY_ACCESS_CERTIFIER_REPORT_DECLINED_TEMPLATE_ID"]
                )
            ]

            assert len(data_provider_emails) == expected_data_provider_emails
            assert len(certifier_emails) == expected_certifier_emails

        def test_decline_when_collection_closed(
            self, factories, submission_awaiting_sign_off, certifier_user, mock_notification_service_calls
        ):
            submission_awaiting_sign_off.collection.status = CollectionStatusEnum.CLOSED
            helper = SubmissionHelper(submission_awaiting_sign_off)

            with pytest.raises(ValueError, match="immutable state"):
                helper.decline_certification(certifier_user, "reason")

            assert len(mock_notification_service_calls) == 0

    class TestSubmissionReopened:
        def test_submission_reopened_grant_team(self, grant_team_user, submission_submitted) -> None:
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED
            for form in helper.get_ordered_visible_forms():
                assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

            helper.reopen_submission(user=grant_team_user, reopened_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            assert helper.reopened_reason == "Test reason"
            assert helper.reopened_by == grant_team_user
            for form in helper.get_ordered_visible_forms():
                assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

        def test_submission_reopened_platform_admin(self, platform_admin_user, submission_submitted) -> None:
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED

            helper.reopen_submission(user=platform_admin_user, reopened_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            assert helper.reopened_reason == "Test reason"
            assert helper.reopened_by == platform_admin_user

        def test_submission_reopened_fails_when_report_closed(self, grant_team_user, submission_submitted) -> None:
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED
            collection = submission_submitted.collection
            collection.status = CollectionStatusEnum.CLOSED

            with pytest.raises(CollectionIsNotOpenError, match="collection is not open"):
                helper.reopen_submission(user=grant_team_user, reopened_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.SUBMITTED

        def test_submission_reopened_fails_when_submission_not_submitted(
            self, grant_team_user, submission_awaiting_sign_off
        ) -> None:
            helper = SubmissionHelper(submission_awaiting_sign_off)
            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

            with pytest.raises(SubmissionIsNotSubmittedError, match="it is not submitted"):
                helper.reopen_submission(user=grant_team_user, reopened_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        @pytest.mark.parametrize(
            "user_fixture",
            [
                "data_provider_user",
                "form_designer_user",
                "platform_member_user",
                "certifier_user",
                "org_admin_user",
            ],
        )
        def test_submission_reopened_fails_when_not_grant_team_or_platform_admin_user(
            self, request, user_fixture, submission_submitted
        ):
            helper = SubmissionHelper(submission_submitted)
            user = request.getfixturevalue(user_fixture)

            with pytest.raises(SubmissionAuthorisationError, match="does not have permission to reopen the submission"):
                helper.reopen_submission(user=user, reopened_reason="Test reason")

        def test_submission_reopened_notification_emails_requires_certification(
            self,
            app,
            grant_team_user,
            data_provider_user,
            certifier_user,
            submission_submitted,
            mock_notification_service_calls,
        ):
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED

            helper.reopen_submission(user=grant_team_user, reopened_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            assert len(mock_notification_service_calls) == 2
            for call in mock_notification_service_calls:
                assert call.kwargs["template_id"] == app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_REOPENED_TEMPLATE_ID"]

            recipients = [call.kwargs["email_address"] for call in mock_notification_service_calls]
            assert data_provider_user.email in recipients
            assert certifier_user.email in recipients

        def test_submission_reopened_notification_emails_no_certification(
            self,
            app,
            grant_team_user,
            data_provider_user,
            certifier_user,
            submission_submitted,
            mock_notification_service_calls,
        ):
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED

            submission_submitted.collection.requires_certification = False

            helper.reopen_submission(user=grant_team_user, reopened_reason="Test reason")

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS
            assert len(mock_notification_service_calls) == 1
            for call in mock_notification_service_calls:
                assert call.kwargs["template_id"] == app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_REOPENED_TEMPLATE_ID"]

            recipients = [call.kwargs["email_address"] for call in mock_notification_service_calls]
            assert data_provider_user.email in recipients
            assert certifier_user.email not in recipients

        def test_reopen_submission_multi_submissions(self, grant_team_user, submission_submitted_multiple_submissions):
            submission_1 = submission_submitted_multiple_submissions[0]
            submission_2 = submission_submitted_multiple_submissions[1]
            helper_1 = SubmissionHelper(submission_1)
            helper_2 = SubmissionHelper(submission_2)
            assert helper_1.status == SubmissionStatusEnum.SUBMITTED
            assert helper_2.status == SubmissionStatusEnum.SUBMITTED

            helper_2.reopen_submission(grant_team_user, reopened_reason="Test reason")
            assert helper_1.status == SubmissionStatusEnum.SUBMITTED
            assert helper_2.status == SubmissionStatusEnum.IN_PROGRESS

    class TestSubmissionChangesRequested:
        def test_request_changes_stores_reason_and_section_ids(self, grant_team_user, submission_submitted) -> None:
            form = submission_submitted.collection.forms[0]
            helper = SubmissionHelper(submission_submitted)
            assert helper.status == SubmissionStatusEnum.SUBMITTED

            helper.request_changes_submission(
                user=grant_team_user,
                changes_requested_reason="Please fix section 1",
                section_ids=[str(form.id)],
            )

            assert helper.status == SubmissionStatusEnum.CHANGES_REQUESTED
            assert helper.changes_requested_reason == "Please fix section 1"
            assert helper.section_ids == [str(form.id)]
            assert helper.changes_requested_by == grant_team_user

        def test_request_changes_fails_when_not_authorised(self, data_provider_user, submission_submitted) -> None:
            helper = SubmissionHelper(submission_submitted)

            with pytest.raises(
                SubmissionAuthorisationError,
                match="User does not have permission to request changes to the submission ",
            ):
                helper.request_changes_submission(
                    user=data_provider_user,
                    changes_requested_reason="Test reason",
                    section_ids=[],
                )

        def test_request_changes_fails_when_collection_closed(self, grant_team_user, submission_submitted) -> None:
            helper = SubmissionHelper(submission_submitted)
            submission_submitted.collection.status = CollectionStatusEnum.CLOSED

            with pytest.raises(CollectionIsNotOpenError, match="collection is not open"):
                helper.request_changes_submission(
                    user=grant_team_user, changes_requested_reason="Test reason", section_ids=[]
                )

        def test_request_changes_with_section_ids_only_resets_matching_forms(
            self, grant_team_user, submission_submitted, factories
        ) -> None:
            first_form = submission_submitted.collection.forms[0]
            second_form = factories.form.create(collection=submission_submitted.collection)

            # make 2nd form's status COMPLETE
            second_question = factories.question.create(form=second_form)
            submission_submitted.data_manager.set(second_question, TextSingleLineAnswer("Answer"))
            factories.submission_event.create(
                submission=submission_submitted,
                related_entity_id=second_form.id,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                created_by=grant_team_user,
            )

            helper = SubmissionHelper(submission_submitted)
            helper.request_changes_submission(
                user=grant_team_user,
                changes_requested_reason="Please fix section 2",
                section_ids=[str(second_form.id)],
            )

            event_ids = [
                event.related_entity_id
                for event in submission_submitted.events
                if event.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
            ]

            assert helper._calculate_submission_status() == SubmissionStatusEnum.CHANGES_REQUESTED

            # section not in the section_ids is unchanged
            assert first_form.id not in event_ids
            assert helper.get_status_for_form(first_form) == TasklistSectionStatusEnum.COMPLETED

            # section in the section_ids is changed and event is created
            assert second_form.id in event_ids
            assert helper.get_status_for_form(second_form) == TasklistSectionStatusEnum.CHANGES_REQUESTED

        def test_request_changes_without_section_ids_resets_all_forms(
            self, grant_team_user, submission_submitted
        ) -> None:
            first_form = submission_submitted.collection.forms[0]

            helper = SubmissionHelper(submission_submitted)
            helper.request_changes_submission(
                user=grant_team_user,
                changes_requested_reason="Please fix section 2",
                section_ids=[],
            )

            event_ids = [
                event.related_entity_id
                for event in submission_submitted.events
                if event.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
            ]

            assert first_form.id in event_ids
            assert helper.get_status_for_form(first_form) == TasklistSectionStatusEnum.IN_PROGRESS
            assert helper._calculate_submission_status() == SubmissionStatusEnum.CHANGES_REQUESTED

        def test_request_changes_sends_notifications(
            self,
            grant_team_user,
            data_provider_user,
            certifier_user,
            submission_submitted,
            mock_notification_service_calls,
        ) -> None:
            helper = SubmissionHelper(submission_submitted)

            helper.request_changes_submission(
                user=grant_team_user, changes_requested_reason="Test reason", section_ids=[]
            )

            assert len(mock_notification_service_calls) == 2
            recipients = [call.kwargs["email_address"] for call in mock_notification_service_calls]
            assert data_provider_user.email in recipients
            assert certifier_user.email in recipients

    class TestLastUpdatedAt:
        @pytest.mark.freeze_time("2026-03-09 12:00:00")
        def test_last_updated_at_utc_returns_last_submission_event_utc(
            self, factories, submission_ready_to_submit, data_provider_user, certifier_user
        ):
            helper = SubmissionHelper(submission_ready_to_submit)
            submission_event = factories.submission_event.create(
                submission=submission_ready_to_submit,
                event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
                created_by=data_provider_user,
                created_at_utc=datetime(2026, 4, 12, 0, 0, 0),
            )
            assert helper.submitted_at_utc is None
            assert helper.certified_at_utc is None
            assert helper.sent_for_certification_at_utc == submission_event.created_at_utc
            assert helper.last_updated_at_utc == submission_event.created_at_utc

            decline_event = factories.submission_event.create(
                submission=submission_ready_to_submit,
                event_type=SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER,
                created_by=certifier_user,
                created_at_utc=datetime(2026, 4, 13, 0, 0, 0),
            )
            assert helper.submitted_at_utc is None
            assert helper.certified_at_utc is None
            assert helper.sent_for_certification_at_utc == submission_event.created_at_utc
            assert helper.last_updated_at_utc == decline_event.created_at_utc

            submission_time = datetime(2026, 4, 14, 0, 0, 0)
            factories.submission_event.create(
                submission=submission_ready_to_submit,
                event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
                created_by=certifier_user,
                created_at_utc=submission_time,
            )
            factories.submission_event.create(
                submission=submission_ready_to_submit,
                event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
                created_by=certifier_user,
                created_at_utc=submission_time,
            )
            assert helper.certified_at_utc == submission_time
            assert helper.submitted_at_utc == submission_time
            assert helper.last_updated_at_utc == submission_time

        def test_last_updated_at_utc_returns_updated_at_when_no_submission_events(self, submission_in_progress):
            helper = SubmissionHelper(submission_in_progress)
            assert helper.submitted_at_utc is None
            assert helper.certified_at_utc is None
            assert helper.last_updated_at_utc == helper.submission.updated_at_utc

    class TestGetDataProvidersForLifecycleEmails:
        def test_returns_correct_data_providers(self, factories):
            gr = factories.grant_recipient.create()
            data_provider_1 = factories.user.create()
            factories.user_role.create(
                user=data_provider_1,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )
            data_provider_2 = factories.user.create()
            factories.user_role.create(
                user=data_provider_2,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )
            certifier_1 = factories.user.create()
            factories.user_role.create(
                user=certifier_1,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )
            certifier_2 = factories.user.create()
            factories.user_role.create(
                user=certifier_2,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )

            preview_submission = factories.submission.create(grant_recipient=gr, mode=SubmissionModeEnum.PREVIEW)
            test_submission = factories.submission.create(grant_recipient=gr, mode=SubmissionModeEnum.TEST)
            live_submission = factories.submission.create(grant_recipient=gr, mode=SubmissionModeEnum.LIVE)

            assert SubmissionHelper(preview_submission)._data_providers_for_lifecycle_emails(data_provider_1) == []
            assert SubmissionHelper(test_submission)._data_providers_for_lifecycle_emails(data_provider_1) == [
                data_provider_1
            ]
            assert set(SubmissionHelper(live_submission)._data_providers_for_lifecycle_emails(data_provider_1)) == {
                data_provider_1,
                data_provider_2,
            }

    class TestGetCertifiersForLifecycleEmails:
        def test_returns_correct_certifiers(self, factories):
            gr = factories.grant_recipient.create()
            data_provider_1 = factories.user.create()
            factories.user_role.create(
                user=data_provider_1,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )
            data_provider_2 = factories.user.create()
            factories.user_role.create(
                user=data_provider_2,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )
            certifier_1 = factories.user.create()
            factories.user_role.create(
                user=certifier_1,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )
            certifier_2 = factories.user.create()
            factories.user_role.create(
                user=certifier_2,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            )

            preview_submission = factories.submission.create(grant_recipient=gr, mode=SubmissionModeEnum.PREVIEW)
            test_submission = factories.submission.create(grant_recipient=gr, mode=SubmissionModeEnum.TEST)
            live_submission = factories.submission.create(grant_recipient=gr, mode=SubmissionModeEnum.LIVE)

            assert SubmissionHelper(preview_submission)._certifiers_for_lifecycle_emails(certifier_1) == []
            assert SubmissionHelper(test_submission)._certifiers_for_lifecycle_emails(certifier_1) == [certifier_1]
            assert set(SubmissionHelper(live_submission)._certifiers_for_lifecycle_emails(certifier_1)) == {
                certifier_1,
                certifier_2,
            }

    class TestPreviousSubmissionData:
        def test_returns_none_when_no_previous_snapshot_exists(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.previous_submission_data is None

        def test_returns_data_manager_when_previous_snapshot_exists(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("original"))],
            )

            # get a copy of the initial data that won't be mutated
            previous_data = deepcopy(submission.data_manager.data)

            # Update answer
            submission.data_manager.set(question, TextSingleLineAnswer("updated"))

            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]
            helper = SubmissionHelper(submission)

            assert helper.previous_submission_data is not None
            assert helper.previous_submission_data.get(question) == TextSingleLineAnswer("original")

    class TestGetPreviousAnswerForQuestion:
        def test_returns_none_when_no_previous_snapshot_exists(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_previous_answer_for_question(question.id) is None

        def test_returns_previous_answer(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("original"))],
            )

            # get a copy of the initial data that won't be mutated
            previous_data = deepcopy(submission.data_manager.data)

            submission.data_manager.set(question, TextSingleLineAnswer("updated"))
            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]

            helper = SubmissionHelper(submission)

            assert helper.get_previous_answer_for_question(question.id) == TextSingleLineAnswer("original")

        def test_returns_previous_for_multi_question_answers(self, factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(
                collection=group.form.collection,
                answers=[
                    FactoryAnswer(question, TextSingleLineAnswer("original 0"), add_another_index=0),
                    FactoryAnswer(question, TextSingleLineAnswer("original 1"), add_another_index=1),
                ],
            )

            # get a copy of the initial data that won't be mutated
            previous_data = deepcopy(submission.data_manager.data)

            # we invert the answers
            submission.data_manager.set(question, TextSingleLineAnswer("original 1"), add_another_index=0)
            submission.data_manager.set(question, TextSingleLineAnswer("original 0"), add_another_index=1)

            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]

            helper = SubmissionHelper(submission)

            # we are fetching the previous answers at the previous index
            assert helper.get_previous_answer_for_question(question.id, add_another_index=0) == TextSingleLineAnswer(
                "original 0"
            )
            assert helper.get_previous_answer_for_question(question.id, add_another_index=1) == TextSingleLineAnswer(
                "original 1"
            )

            # assert for SubmissionDataAddAnotherIndexInvalid cases
            assert helper.get_previous_answer_for_question(question.id, add_another_index=2) is None

    class TestHasAnswerChangedSincePrevious:
        def test_returns_false_when_no_previous_snapshot_exists(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("answer"))],
            )
            helper = SubmissionHelper(submission)

            assert helper.has_answer_changed_since_previous(question.id) is False

        @pytest.mark.parametrize(
            "initial_answer, updated_answer, expected",
            [
                pytest.param("same", "same", False, id="unchanged"),
                pytest.param("original", "updated", True, id="changed"),
            ],
        )
        def test_answer_changed_since_previous(self, factories, initial_answer, updated_answer, expected):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer(initial_answer))],
            )
            previous_data = deepcopy(submission.data_manager.data)
            submission.data_manager.set(question, TextSingleLineAnswer(updated_answer))
            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]
            helper = SubmissionHelper(submission)

            assert helper.has_answer_changed_since_previous(question.id) is expected

        def test_answer_changed_since_previous_with_add_another_index(self, factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(
                collection=group.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("original"), add_another_index=0)],
            )
            previous_data = deepcopy(submission.data_manager.data)
            submission.data_manager.set(question, TextSingleLineAnswer("updated"), add_another_index=0)
            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]

            helper = SubmissionHelper(submission)

            assert helper.has_answer_changed_since_previous(question.id, add_another_index=0) is True

    class TestHasFormChangedSincePreviousSubmission:
        def test_returns_false_when_no_previous_snapshot_exists(self, factories):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer("answer"))],
            )

            helper = SubmissionHelper(submission)

            assert helper.has_form_changed_since_previous_submission(question.form) is False

        @pytest.mark.parametrize(
            "initial_answer, updated_answer, expected",
            [
                pytest.param("same", "same", False, id="unchanged"),
                pytest.param("original", "updated", True, id="changed"),
            ],
        )
        def test_form_changed_since_previous(self, factories, initial_answer, updated_answer, expected):
            question = factories.question.build()
            submission = factories.submission.build(
                collection=question.form.collection,
                answers=[FactoryAnswer(question, TextSingleLineAnswer(initial_answer))],
            )
            previous_data = deepcopy(submission.data_manager.data)
            submission.data_manager.set(question, TextSingleLineAnswer(updated_answer))
            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]

            helper = SubmissionHelper(submission)

            assert helper.has_form_changed_since_previous_submission(question.form) is expected

        @pytest.mark.parametrize(
            "initial_answers, updated_answers, expected",
            [
                pytest.param(["original 0", "original 1"], ["original 0", "original 1"], False, id="unchanged"),
                pytest.param(["original 0", "original 1"], ["original 1", "original 0"], True, id="swapped_are_diff"),
                pytest.param(["original 0", "original 1"], ["updated 0", "updated 1"], True, id="different"),
                pytest.param(["original 0"], ["original 0", "original 1"], True, id="uneven"),
            ],
        )
        def test_returns_for_changed_multi_question_answers(
            self, factories, initial_answers, updated_answers, expected
        ):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            submission = factories.submission.build(
                collection=group.form.collection,
                answers=[
                    FactoryAnswer(question, TextSingleLineAnswer(answer), add_another_index=index)
                    for index, answer in enumerate(initial_answers)
                ],
            )

            # get a copy of the initial data that won't be mutated
            previous_data = deepcopy(submission.data_manager.data)

            # we invert the answers
            for index, answer in enumerate(updated_answers):
                submission.data_manager.set(question, TextSingleLineAnswer(answer), add_another_index=index)

            submission.events = [
                factories.submission_event.build(
                    submission=submission,
                    event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                    data=SubmissionEventHelper.event_from(
                        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
                        changes_requested_reason="Fix this",
                        submission_data=previous_data,
                        section_ids=[],
                    ),
                )
            ]

            helper = SubmissionHelper(submission)

            assert helper.has_form_changed_since_previous_submission(question.form) is expected


class TestFormResetOnAnswerChange:
    def test_same_section_reset_when_completed(self, db_session, factories):
        question = factories.question.create(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
        form = question.form
        submission = factories.submission.create(collection=form.collection)
        helper = SubmissionHelper(submission)

        helper.submit_answer_for_question(
            question.id,
            build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="First answer"
            ),
            submission.created_by,
        )
        helper.toggle_form_completed(form, submission.created_by, True)
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

        helper.submit_answer_for_question(
            question.id,
            build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Changed answer"
            ),
            user=submission.created_by,
        )

        reset_events = [
            e
            for e in submission.events
            if e.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
            and e.related_entity_id == form.id
        ]
        assert len(reset_events) == 1
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

    def test_same_section_no_reset_when_not_completed(self, db_session, factories):
        question = factories.question.create(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
        form = question.form
        submission = factories.submission.create(collection=form.collection)
        helper = SubmissionHelper(submission)

        helper.submit_answer_for_question(
            question.id,
            build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="First answer"
            ),
            submission.created_by,
        )
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

        helper.submit_answer_for_question(
            question.id,
            build_question_form([question], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Changed answer"
            ),
            submission.created_by,
        )

        reset_events = [
            e for e in submission.events if e.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
        ]
        assert len(reset_events) == 0

    def test_cross_section_reset_when_visibility_changes(self, db_session, factories):
        collection = factories.collection.create()
        form_a = factories.form.create(collection=collection, order=0)
        form_b = factories.form.create(collection=collection, order=1)
        user = factories.user.create()

        q_a = factories.question.create(
            form=form_a,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q_b1 = factories.question.create(form=form_b, order=0)
        factories.question.create(
            form=form_b,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
            order=1,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(subject_reference=ExpressionReference.from_question(q_a), minimum_value=50),
                    ExpressionType.CONDITION,
                    user,
                )
            ],
        )

        submission = factories.submission.create(
            collection=collection,
            created_by=user,
            answers=[
                FactoryAnswer(q_a, IntegerAnswer(value=10)),
                FactoryAnswer(q_b1, TextSingleLineAnswer("answer b1")),
            ],
        )
        helper = SubmissionHelper(submission)

        helper.toggle_form_completed(form_b, user, True)
        assert helper.get_status_for_form(form_b) == TasklistSectionStatusEnum.COMPLETED

        helper.submit_answer_for_question(
            q_a.id,
            build_question_form([q_a], evaluation_context=EC(), interpolation_context=EC())(**{q_a.safe_qid: 100}),
            user=user,
        )

        reset_events_b = [
            e
            for e in submission.events
            if e.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
            and e.related_entity_id == form_b.id
        ]
        assert len(reset_events_b) == 1

    def test_cross_section_no_reset_when_visibility_unchanged(self, db_session, factories):
        collection = factories.collection.create()
        form_a = factories.form.create(collection=collection, order=0)
        form_b = factories.form.create(collection=collection, order=1)
        user = factories.user.create()

        q_a = factories.question.create(
            form=form_a,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q_b1 = factories.question.create(form=form_b, order=0)
        factories.question.create(
            form=form_b,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
            order=1,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(subject_reference=ExpressionReference.from_question(q_a), minimum_value=50),
                    ExpressionType.CONDITION,
                    user,
                )
            ],
        )

        submission = factories.submission.create(
            collection=collection,
            answers=[
                FactoryAnswer(q_a, IntegerAnswer(value=10)),
                FactoryAnswer(q_b1, TextSingleLineAnswer("answer b1")),
            ],
        )
        helper = SubmissionHelper(submission)

        helper.toggle_form_completed(form_b, user, True)
        assert helper.get_status_for_form(form_b) == TasklistSectionStatusEnum.COMPLETED

        helper.submit_answer_for_question(
            q_a.id,
            build_question_form([q_a], evaluation_context=EC(), interpolation_context=EC())(**{q_a.safe_qid: 20}),
            user=user,
        )

        reset_events_b = [
            e
            for e in submission.events
            if e.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
            and e.related_entity_id == form_b.id
        ]
        assert len(reset_events_b) == 0

    def test_no_duplicate_events_for_multi_question_component(self, db_session, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), order=0)
        q2 = factories.question.create(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"), order=1)

        submission = factories.submission.create(collection=form.collection)
        helper = SubmissionHelper(submission)

        helper.submit_answer_for_question(
            q1.id,
            build_question_form([q1], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Answer 1"
            ),
            submission.created_by,
        )
        helper.submit_answer_for_question(
            q2.id,
            build_question_form([q2], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994295="Answer 2"
            ),
            submission.created_by,
        )
        helper.toggle_form_completed(form, user, True)
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

        helper.submit_answer_for_question(
            q1.id,
            build_question_form([q1], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="Changed 1"
            ),
            submission.created_by,
        )
        helper.submit_answer_for_question(
            q2.id,
            build_question_form([q2], evaluation_context=EC(), interpolation_context=EC())(
                q_d696aebc49d24170a92fb6ef42994295="Changed 2"
            ),
            submission.created_by,
        )

        reset_events = [
            e
            for e in submission.events
            if e.event_type == SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS
            and e.related_entity_id == form.id
        ]
        assert len(reset_events) == 1


class TestSubmissionsHelper:
    def test_init_submissions_helper(self, factories):
        collection = factories.collection.create(create_submissions__test=2, create_submissions__live=3)
        collection_from_db = interfaces.collections.get_collection(collection.id)
        assert len(collection_from_db._submissions) == 5

        test_submissions_helper = AllSubmissionsHelper(
            collection=collection_from_db, submission_mode=SubmissionModeEnum.TEST
        )
        assert test_submissions_helper.collection == collection
        assert test_submissions_helper.submission_mode == SubmissionModeEnum.TEST
        assert len(test_submissions_helper.submissions) == 2

        live_submissions_helper = AllSubmissionsHelper(
            collection=collection_from_db, submission_mode=SubmissionModeEnum.LIVE
        )
        assert live_submissions_helper.collection == collection
        assert live_submissions_helper.submission_mode == SubmissionModeEnum.LIVE
        assert len(live_submissions_helper.submissions) == 3

    @pytest.mark.freeze_time("2025-03-01 13:30:00")
    def test_generate_csv_content_check_correct_rows_for_multiple_simple_submissions_every_question_type(
        self, factories
    ):
        num_test_submissions = 3
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=num_test_submissions,
            create_completed_submissions_each_question_type__use_random_data=True,
        )
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = subs_helper.generate_csv_content_for_all_submissions()
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
            "[Export test form] Dog price",
            "[Export test form] Best option",
            "[Export test form] Like cheese",
            "[Export test form] Email address",
            "[Export test form] Website address",
            "[Export test form] Favourite cheeses",
            "[Export test form] Last cheese purchase date",
            "[Export test form] Supporting document",
        ]
        expected_question_data = {}
        for _, submission in subs_helper.submission_helpers.items():
            expected_question_data[submission.reference] = {
                f"[{question.form.title}] {question.name}": submission.submission.data_manager.get(
                    question
                ).get_value_for_text_export()
                for _, question in submission.all_visible_questions.items()
            }
        rows = list(reader)
        for line in rows:
            submission_ref = line["Submission reference"]
            s_helper = subs_helper.get_submission_helper_by_reference(submission_ref)
            assert line["Created by"] == s_helper.created_by_email
            assert line["Created at"] == "2025-03-01 13:30:00"
            for header, value in expected_question_data[submission_ref].items():
                assert line[header] == value

        assert len(rows) == num_test_submissions

    @pytest.mark.freeze_time("2025-03-01 13:30:00")
    def test_generate_csv_content_skipped_questions(self, factories):
        collection = factories.collection.create(create_completed_submissions_conditional_question__test=True)
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = subs_helper.generate_csv_content_for_all_submissions()
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
            s_helper = subs_helper.get_submission_helper_by_reference(submission_ref)
            assert line["Created by"] == s_helper.created_by_email
            assert line["Created at"] == "2025-03-01 13:30:00"
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
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        dependant_question = collection.forms[0].cached_questions[0]
        conditional_question = collection.forms[0].cached_questions[1]

        # Find the submission where question 2 is not expected to be answered it and store some data as though it has
        # previously been answered
        submission = next(
            helper.submission
            for _, helper in subs_helper.submission_helpers.items()
            if helper.cached_get_answer_for_question(dependant_question.id).get_value_for_text_export() == "20"
        )
        submission.data_manager.set(conditional_question, IntegerAnswer(value=120))
        csv_content = subs_helper.generate_csv_content_for_all_submissions()
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

    @pytest.mark.freeze_time("2025-03-01 13:30:00")
    def test_all_question_types_appear_correctly_in_csv_row(self, factories):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_each_question_type__test=1,
            create_completed_submissions_each_question_type__use_random_data=False,
        )
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = subs_helper.generate_csv_content_for_all_submissions()
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
            "[Export test form] Dog price",
            "[Export test form] Best option",
            "[Export test form] Like cheese",
            "[Export test form] Email address",
            "[Export test form] Website address",
            "[Export test form] Favourite cheeses",
            "[Export test form] Last cheese purchase date",
            "[Export test form] Supporting document",
        ]
        assert rows[1] == [
            subs_helper.submissions[0].reference,
            subs_helper.submissions[0].grant_recipient.organisation.name,
            subs_helper.submissions[0].created_by.email,
            "2025-03-01 13:30:00",
            "",
            "",
            "In progress",
            "",
            "test name",
            "Line 1\r\nline2\r\nline 3",
            "123",
            "456.78",
            "Option 0",
            "Yes",
            "test@email.com",
            "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government",
            "Cheddar\nStilton",
            "2025-01-01",
            "test-document.pdf",
        ]

    @pytest.mark.freeze_time("2025-03-01 13:30:00")
    def test_generate_csv_content_add_another(self, factories):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = subs_helper.generate_csv_content_for_all_submissions()
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
            subs_helper.submissions[0].reference,
            subs_helper.submissions[0].grant_recipient.organisation.name,
            subs_helper.submissions[0].created_by.email,
            "2025-03-01 13:30:00",
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
            reference="TEST-001",
            answers=[
                FactoryAnswer(question, TextSingleLineAnswer("first"), add_another_index=0),
                FactoryAnswer(question, TextSingleLineAnswer("second"), add_another_index=1),
                FactoryAnswer(question, TextSingleLineAnswer("third"), add_another_index=2),
            ],
        )
        factories.submission.create(
            collection=group.form.collection,
            mode=SubmissionModeEnum.TEST,
            reference="TEST-002",
            answers=[FactoryAnswer(question, TextSingleLineAnswer("only first"), add_another_index=0)],
        )

        subs_helper = AllSubmissionsHelper(collection=group.form.collection, submission_mode=SubmissionModeEnum.TEST)
        csv_content = subs_helper.generate_csv_content_for_all_submissions()
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
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        json_data = subs_helper.generate_json_content_for_all_submissions()
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
                                "Dog price": {"value": "456.78"},
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
                                "Supporting document": "test-document.pdf",
                            },
                            "name": "Export test form",
                        }
                    ],
                }
            ]
        }

    @pytest.mark.freeze_time("2025-03-01 13:30:00")
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
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.LIVE)
        json_data = subs_helper.generate_json_content_for_all_submissions()
        submissions = json.loads(json_data)

        assert submissions == {
            "submissions": [
                {
                    "created_at_utc": "2025-03-01 13:30:00",
                    "created_by": mock.ANY,
                    "certified_by": "certifier@test.com",
                    "certified_at_utc": "2025-12-01 00:00:00",
                    "grant_recipient": AnyStringMatching(r"Organisation \d+"),
                    "reference": mock.ANY,
                    "status": "In progress",
                    "submitted_at_utc": None,
                    "sections": [
                        {
                            "answers": {
                                "Airspeed velocity": {"value": 123},
                                "Dog price": {"value": "456.78"},
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
                                "Supporting document": "test-document.pdf",
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
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        json_data = subs_helper.generate_json_content_for_all_submissions()
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
        create_submissions_helper_start = datetime.now()
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        create_submissions_helper_duration = datetime.now() - create_submissions_helper_start
        with track_sql_queries() as queries:
            start = datetime.now()
            subs_helper.generate_csv_content_for_all_submissions()
            end = datetime.now()
            generate_csv_content_for_all_submissions_duration = end - start
        total_query_duration = sum(query.duration for query in queries)
        results = {
            "num_test_submissions": num_test_submissions,
            "num_sql_queries": len(queries),
            "factory_duration": str(factory_duration.total_seconds()),
            "create_submissions_helper_duration": str(create_submissions_helper_duration.total_seconds()),
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
        create_submissions_helper_start = datetime.now()
        subs_helper = AllSubmissionsHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        create_submissions_helper_duration = datetime.now() - create_submissions_helper_start
        with track_sql_queries() as queries:
            start = datetime.now()
            subs_helper.generate_csv_content_for_all_submissions()
            end = datetime.now()
            generate_csv_content_for_all_submissions_duration = end - start
        total_query_duration = sum(query.duration for query in queries)
        results = {
            "num_test_submissions": num_test_submissions,
            "num_sql_queries": len(queries),
            "factory_duration": str(factory_duration.total_seconds()),
            "create_submissions_helper_duration": str(create_submissions_helper_duration.total_seconds()),
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
        q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.create(
            question=q2,
            created_by=user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.create(
            collection=form.collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=50)),
                FactoryAnswer(q2, IntegerAnswer(value=100)),
            ],
        )

        helper = SubmissionHelper(submission)
        helper.toggle_form_completed(form, user, True)

        submission.data_manager.set(q1, IntegerAnswer(value=150))
        helper.clear_caches()

        with pytest.raises(ValueError) as e:
            helper.submit(user)

        assert "no longer valid" in str(e.value)

    def test_submit_succeeds_when_all_answers_valid(self, factories, mock_notification_service_calls):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.create(
            question=q2,
            created_by=user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.create(
            collection=form.collection,
            mode=SubmissionModeEnum.TEST,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=50)),
                FactoryAnswer(q2, IntegerAnswer(value=100)),
            ],
        )

        helper = SubmissionHelper(submission)
        helper.toggle_form_completed(form, user, True)

        helper.submit(user)

        assert helper.is_submitted

    def test_certification_fails_when_answer_no_longer_valid(self, factories):
        form = factories.form.create()
        user = factories.user.create()
        q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.create(
            question=q2,
            created_by=user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        collection = form.collection
        collection.requires_certification = True

        submission = factories.submission.create(
            collection=collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=50)),
                FactoryAnswer(q2, IntegerAnswer(value=100)),
            ],
        )

        helper = SubmissionHelper(submission)
        helper.toggle_form_completed(form, user, True)

        submission.data_manager.set(q1, IntegerAnswer(value=150))
        helper.clear_caches()

        with pytest.raises(ValueError) as e:
            helper.mark_as_sent_for_certification(user)

        assert "no longer valid" in str(e.value)
