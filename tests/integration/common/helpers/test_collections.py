import csv
import uuid
from io import StringIO

import pytest
from immutabledict import immutabledict

from app.common.collections.forms import build_question_form
from app.common.collections.types import NOT_ASKED, Integer, SingleChoiceFromList, TextMultiLine, TextSingleLine, YesNo
from app.common.data import interfaces
from app.common.data.types import QuestionDataType, SubmissionModeEnum, SubmissionStatusEnum, TasklistTaskStatusEnum
from app.common.expressions import ExpressionContext
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
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_answer_for_question(question.id) is None

            form = build_question_form(question, expression_context=EC())(
                q_d696aebc49d24170a92fb6ef42994294="User submitted data"
            )
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == TextSingleLine("User submitted data")

        def test_get_data_maps_type(self, db_session, factories):
            question = factories.question.build(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.INTEGER
            )
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form(question, expression_context=EC())(q_d696aebc49d24170a92fb6ef42994294=5)
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == Integer(5)

        def test_can_get_falsey_answers(self, db_session, factories):
            question = factories.question.build(
                id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"), data_type=QuestionDataType.INTEGER
            )
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form(question, expression_context=EC())(q_d696aebc49d24170a92fb6ef42994294=0)
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == Integer(0)

        def test_cannot_submit_answer_on_submitted_submission(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form(question, expression_context=EC())(
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
            form_two = factories.form.build(section=form.section)
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            factories.question.build(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"))

            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.form_data == {}

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 7, "Update this test if adding new questions"

            form = factories.form.build()
            form_two = factories.form.build(section=form.section)
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

            submission = factories.submission.build(
                collection=form.section.collection,
                data={
                    str(q1.id): TextSingleLine("answer").get_value_for_submission(),
                    str(q2.id): TextMultiLine("answer\nthis").get_value_for_submission(),
                    str(q3.id): Integer(50).get_value_for_submission(),
                    str(q4.id): YesNo(True).get_value_for_submission(),  # ty: ignore[missing-argument]
                    str(q5.id): SingleChoiceFromList(key="my-key", label="My label").get_value_for_submission(),
                    str(q6.id): TextSingleLine("name@example.com").get_value_for_submission(),
                    str(q7.id): TextSingleLine("https://example.com").get_value_for_submission(),
                },
            )
            helper = SubmissionHelper(submission)

            assert helper.form_data == {
                "q_d696aebc49d24170a92fb6ef42994294": "answer",
                "q_d696aebc49d24170a92fb6ef42994295": "answer\nthis",
                "q_d696aebc49d24170a92fb6ef42994296": 50,
                "q_d696aebc49d24170a92fb6ef42994297": True,
                "q_d696aebc49d24170a92fb6ef42994298": "my-key",
                "q_d696aebc49d24170a92fb6ef42994299": "name@example.com",
                "q_d696aebc49d24170a92fb6ef4299429a": "https://example.com",
            }

    class TestExpressionContext:
        def test_no_submission_data(self, factories):
            form = factories.form.build()
            form_two = factories.form.build(section=form.section)
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            factories.question.build(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296"))

            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.expression_context == ExpressionContext()

        def test_with_submission_data(self, factories):
            assert len(QuestionDataType) == 7, "Update this test if adding new questions"

            form = factories.form.build()
            form_two = factories.form.build(section=form.section)
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
            submission = factories.submission.build(
                collection=form.section.collection,
                data={
                    str(q1.id): TextSingleLine("answer").get_value_for_submission(),
                    str(q2.id): TextMultiLine("answer\nthis").get_value_for_submission(),
                    str(q3.id): Integer(50).get_value_for_submission(),
                    str(q4.id): YesNo(True).get_value_for_submission(),  # ty: ignore[missing-argument]
                    str(q5.id): SingleChoiceFromList(key="my-key", label="My label").get_value_for_submission(),
                    str(q6.id): TextSingleLine("name@example.com").get_value_for_submission(),
                    str(q7.id): TextSingleLine("https://example.com").get_value_for_submission(),
                },
            )
            helper = SubmissionHelper(submission)

            assert helper.expression_context == ExpressionContext(
                from_submission=immutabledict(
                    {
                        "q_d696aebc49d24170a92fb6ef42994294": "answer",
                        "q_d696aebc49d24170a92fb6ef42994295": "answer\nthis",
                        "q_d696aebc49d24170a92fb6ef42994296": 50,
                        "q_d696aebc49d24170a92fb6ef42994297": True,
                        "q_d696aebc49d24170a92fb6ef42994298": "my-key",
                        "q_d696aebc49d24170a92fb6ef42994299": "name@example.com",
                        "q_d696aebc49d24170a92fb6ef4299429a": "https://example.com",
                    }
                )
            )

    class TestStatuses:
        def test_form_status_based_on_questions(self, db_session, factories):
            form = factories.form.build()
            form_two = factories.form.build(section=form.section)
            question_one = factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            question_two = factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))
            question_three = factories.question.build(
                form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994296")
            )

            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.NOT_STARTED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question_one.id,
                build_question_form(question_one, expression_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form(question_two, expression_context=EC())(
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
                build_question_form(question_three, expression_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994296="User submitted data"
                ),
            )
            assert helper.get_status_for_form(form_two) == SubmissionStatusEnum.IN_PROGRESS
            assert helper.get_tasklist_status_for_form(form_two) == TasklistTaskStatusEnum.IN_PROGRESS

        def test_form_status_with_no_questions(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)
            assert helper.get_status_for_form(form) == SubmissionStatusEnum.NOT_STARTED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.NO_QUESTIONS

        def test_submission_status_based_on_forms(self, db_session, factories):
            question = factories.question.build(id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            form_two = factories.form.build(section=question.form.section)
            question_two = factories.question.build(form=form_two, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994295"))

            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question.id,
                build_question_form(question, expression_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(question.form) == TasklistTaskStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id,
                build_question_form(question_two, expression_context=EC())(
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
            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.toggle_form_completed(form, submission.created_by, True)

            assert str(e.value) == AnyStringMatching(
                r"Could not mark form id=[a-z0-9-]+ as complete because not all questions have been answered."
            )

            helper.submit_answer_for_question(
                question.id,
                build_question_form(question, expression_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )
            helper.toggle_form_completed(form, submission.created_by, True)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED
            assert helper.get_tasklist_status_for_form(form) == TasklistTaskStatusEnum.COMPLETED

        def test_toggle_form_status_doesnt_change_status_if_already_completed(self, db_session, factories):
            section = factories.section.build()
            form = factories.form.build(section=section)

            # a second form with questions ensures nothing is conflating the submission and individual form statuses
            second_form = factories.form.build(section=section)

            question = factories.question.build(form=form, id=uuid.UUID("d696aebc-49d2-4170-a92f-b6ef42994294"))
            factories.question.build(form=second_form)

            submission = factories.submission.build(collection=section.collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id,
                build_question_form(question, expression_context=EC())(
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
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id,
                build_question_form(question, expression_context=EC())(
                    q_d696aebc49d24170a92fb6ef42994294="User submitted data"
                ),
            )

            with pytest.raises(ValueError) as e:
                helper.submit(submission.created_by)

            assert str(e.value) == AnyStringMatching(
                r"Could not submit submission id=[a-z0-9-]+ because not all forms are complete."
            )


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
            "Created time UTC",
            "[Export test form] Your name",
            "[Export test form] Your quest",
            "[Export test form] Airspeed velocity",
            "[Export test form] Best option",
            "[Export test form] Like cheese",
            "[Export test form] Email address",
            "[Export test form] Website address",
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
            assert line["Created time UTC"] == s_helper.created_at_utc.isoformat()
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
            "Created time UTC",
            "[Export test form] Number of cups of tea",
            "[Export test form] Tea bag pack size",
            "[Export test form] Favourite dunking biscuit",
        ]
        line1 = next(reader)
        submission_ref = line1["Submission reference"]
        s_helper = c_helper.get_submission_helper_by_reference(submission_ref)
        assert line1["Created by"] == s_helper.created_by_email
        assert line1["Created time UTC"] == s_helper.created_at_utc.isoformat()
        assert line1["[Export test form] Number of cups of tea"] == "40"
        assert line1["[Export test form] Tea bag pack size"] == "80"
        assert line1["[Export test form] Favourite dunking biscuit"] == "digestive"

        line2 = next(reader)
        submission_ref = line2["Submission reference"]
        s_helper = c_helper.get_submission_helper_by_reference(submission_ref)
        assert line2["Created by"] == s_helper.created_by_email
        assert line2["Created time UTC"] == s_helper.created_at_utc.isoformat()
        assert line2["[Export test form] Number of cups of tea"] == "20"
        assert line2["[Export test form] Tea bag pack size"] == "NOT_ASKED"
        assert line2["[Export test form] Favourite dunking biscuit"] == "digestive"

    def test_generate_csv_content_skipped_questions_previously_answered(self, factories):
        collection = factories.collection.create(create_completed_submissions_conditional_question__test=True)
        c_helper = CollectionHelper(collection=collection, submission_mode=SubmissionModeEnum.TEST)
        question_id = collection.sections[0].forms[0].questions[1].id
        submission = c_helper.submissions[1]
        submission.data[str(question_id)] = 120
        csv_content = c_helper.generate_csv_content_for_all_submissions()
        reader = csv.DictReader(StringIO(csv_content))

        assert reader.fieldnames == [
            "Submission reference",
            "Created by",
            "Created time UTC",
            "[Export test form] Number of cups of tea",
            "[Export test form] Tea bag pack size",
            "[Export test form] Favourite dunking biscuit",
        ]
        line1 = next(reader)
        assert line1["[Export test form] Tea bag pack size"] == "80"

        # Check that the second submission says NOT_ASKED for question 2 because based on the value of question 1
        # it should not be visible
        line2 = next(reader)
        assert line2["[Export test form] Tea bag pack size"] == NOT_ASKED

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
            "Created time UTC",
            "[Export test form] Your name",
            "[Export test form] Your quest",
            "[Export test form] Airspeed velocity",
            "[Export test form] Best option",
            "[Export test form] Like cheese",
            "[Export test form] Email address",
            "[Export test form] Website address",
        ]
        assert rows[1] == [
            c_helper.submissions[0].reference,
            c_helper.submissions[0].created_by.email,
            c_helper.submissions[0].created_at_utc.isoformat(),
            "test name",
            "Line 1\r\nline2\r\nline 3",
            "123",
            "Option 0",
            "Yes",
            "test@email.com",
            "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government",
        ]
