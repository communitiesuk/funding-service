import pytest

from app.common.collections.forms import build_question_form
from app.common.data.types import QuestionDataType, SubmissionStatusEnum
from app.common.helpers.collections import Integer, SubmissionHelper, TextSingleLine
from tests.utils import AnyStringMatching


class TestSubmissionHelper:
    class TestGetAndSubmitAnswerForQuestion:
        def test_submit_valid_data(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_answer_for_question(question.id) is None

            form = build_question_form(question)(question="User submitted data")
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == TextSingleLine("User submitted data")

        def test_get_data_maps_type(self, db_session, factories):
            question = factories.question.build(data_type=QuestionDataType.INTEGER)
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form(question)(question=5)
            helper.submit_answer_for_question(question.id, form)

            assert helper.get_answer_for_question(question.id) == Integer(5)

        def test_cannot_submit_answer_on_submitted_submission(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            form = build_question_form(question)(question="User submitted data")
            helper.submit_answer_for_question(question.id, form)
            helper.toggle_form_completed(question.form, submission.created_by, True)
            helper.submit(submission.created_by)

            with pytest.raises(ValueError) as e:
                helper.submit_answer_for_question(question.id, form)

            assert str(e.value) == AnyStringMatching(
                "Could not submit answer for question_id=[a-z0-9-]+ "
                "because submission id=[a-z0-9-]+ is already submitted."
            )

    class TestStatuses:
        def test_form_status_based_on_questions(self, db_session, factories):
            form = factories.form.build()
            form_two = factories.form.build(section=form.section)
            question_one = factories.question.build(form=form)
            question_two = factories.question.build(form=form)
            question_three = factories.question.build(form=form_two)

            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question_one.id, build_question_form(question_one)(question="User submitted data")
            )

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id, build_question_form(question_two)(question="User submitted data")
            )

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.IN_PROGRESS

            helper.toggle_form_completed(form, submission.created_by, True)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED

            # make sure the second form is unaffected by the first forms status
            helper.submit_answer_for_question(
                question_three.id, build_question_form(question_three)(question="User submitted data")
            )
            assert helper.get_status_for_form(form_two) == SubmissionStatusEnum.IN_PROGRESS

        def test_form_status_with_no_questions(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)
            assert helper.get_status_for_form(form) == SubmissionStatusEnum.NOT_STARTED

        def test_submission_status_based_on_forms(self, db_session, factories):
            question = factories.question.build()
            form_two = factories.form.build(section=question.form.section)
            question_two = factories.question.build(form=form_two)

            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            assert helper.status == SubmissionStatusEnum.NOT_STARTED

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED
            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit_answer_for_question(
                question_two.id, build_question_form(question_two)(question="User submitted data")
            )
            helper.toggle_form_completed(question_two.form, submission.created_by, True)

            assert helper.get_status_for_form(question_two.form) == SubmissionStatusEnum.COMPLETED

            assert helper.status == SubmissionStatusEnum.IN_PROGRESS

            helper.submit(submission.created_by)

            assert helper.status == SubmissionStatusEnum.COMPLETED

        def test_toggle_form_status(self, db_session, factories):
            question = factories.question.build()
            form = question.form
            submission = factories.submission.build(collection=form.section.collection)
            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.toggle_form_completed(form, submission.created_by, True)

            assert str(e.value) == AnyStringMatching(
                r"Could not mark form id=[a-z0-9-]+ as complete because not all questions have been answered."
            )

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )
            helper.toggle_form_completed(form, submission.created_by, True)

            assert helper.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED

        def test_toggle_form_status_doesnt_change_status_if_already_completed(self, db_session, factories):
            section = factories.section.build()
            form = factories.form.build(section=section)

            # a second form with questions ensures nothing is conflating the submission and individual form statuses
            second_form = factories.form.build(section=section)

            question = factories.question.build(form=form)
            factories.question.build(form=second_form)

            submission = factories.submission.build(collection=section.collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )
            helper.toggle_form_completed(question.form, submission.created_by, True)

            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED

            helper.toggle_form_completed(question.form, submission.created_by, True)
            assert helper.get_status_for_form(question.form) == SubmissionStatusEnum.COMPLETED
            assert len(submission.events) == 1

        def test_submit_submission_rejected_if_not_complete(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)
            helper = SubmissionHelper(submission)

            helper.submit_answer_for_question(
                question.id, build_question_form(question)(question="User submitted data")
            )

            with pytest.raises(ValueError) as e:
                helper.submit(submission.created_by)

            assert str(e.value) == AnyStringMatching(
                r"Could not submit submission id=[a-z0-9-]+ because not all forms are complete."
            )
