from unittest.mock import Mock

import pytest

from app.common.collections.runner import FormRunner
from app.common.collections.types import TextSingleLineAnswer
from app.common.data.types import FormRunnerState, QuestionDataType, QuestionPresentationOptions
from app.common.helpers.collections import SubmissionHelper


class TestFormRunner:
    def test_form_runner_loads_and_sets_context(self, factories):
        question = factories.question.build()
        submission = factories.submission.build(collection=question.form.section.collection)
        helper = SubmissionHelper(submission)

        question_state_context = FormRunner(submission=helper, question=question, source=None)
        assert question_state_context.component == question
        assert question_state_context.form == question.form
        assert question_state_context.question_form is not None

        check_your_answers_context = FormRunner(submission=helper, form=question.form, source=None)
        assert check_your_answers_context.component is None
        assert check_your_answers_context.form == question.form
        assert check_your_answers_context.check_your_answers_form is not None

        tasklist_context = FormRunner(submission=helper, source=None)
        assert tasklist_context.component is None
        assert tasklist_context.form is None
        assert tasklist_context.tasklist_form is not None

    def test_form_runner_loads_and_sets_context_for_same_page_group(self, factories):
        group = factories.group.build(
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        q1 = factories.question.build(parent=group, form=group.form)
        q2 = factories.question.build(parent=group, form=group.form)
        submission = factories.submission.build(collection=group.form.section.collection)
        helper = SubmissionHelper(submission)

        runner = FormRunner(submission=helper, question=q1, source=None)

        assert runner.component == group
        assert runner.component.questions == [q1, q2]
        assert runner.question_form is not None

    def test_form_runner_correctly_configures_dynamic_question_form(self, factories):
        question = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        submission = factories.submission.build(
            collection=question.form.section.collection,
            data={str(question.id): TextSingleLineAnswer("An answer").get_value_for_submission()},
        )
        helper = SubmissionHelper(submission)

        runner = FormRunner(submission=helper, question=question, source=None)
        assert runner.question_form.get_question_field(question) is not None
        assert runner.question_form.get_answer_to_question(question) == "An answer"

    def test_form_runner_correctly_configured_dynamic_question_form_for_same_page(self, factories):
        group = factories.group.build(
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        q1 = factories.question.build(parent=group, form=group.form)
        q2 = factories.question.build(parent=group, form=group.form)
        submission = factories.submission.build(
            collection=group.form.section.collection,
            data={
                str(q1.id): TextSingleLineAnswer("An answer for q1").get_value_for_submission(),
                str(q2.id): TextSingleLineAnswer("An answer for q2").get_value_for_submission(),
            },
        )
        helper = SubmissionHelper(submission)

        runner = FormRunner(submission=helper, question=q1, source=None)
        assert runner.question_form.get_question_field(q1) is not None
        assert runner.question_form.get_answer_to_question(q1) == "An answer for q1"
        assert runner.question_form.get_answer_to_question(q2) == "An answer for q2"
        assert runner.question_form.get_question_field(q2) is not None

    def test_calls_mapped_urls_with_the_right_information(self, factories):
        question = factories.question.build()
        second_question = factories.question.build(form=question.form)
        second_form = factories.form.build(section=question.form.section)
        submission = factories.submission.build(collection=question.form.section.collection)
        helper = SubmissionHelper(submission)

        question_mock = Mock(return_value="mock_question_url")
        tasklist_mock = Mock(return_value="mock_tasklist_url")
        check_answers_mock = Mock(return_value="mock_check_answers_url")

        class MappedFormRunner(FormRunner):
            url_map = {
                FormRunnerState.QUESTION: question_mock,
                FormRunnerState.TASKLIST: tasklist_mock,
                FormRunnerState.CHECK_YOUR_ANSWERS: check_answers_mock,
            }

        runner = MappedFormRunner(submission=helper, question=question, source=None)
        url = runner.to_url(FormRunnerState.QUESTION, source=FormRunnerState.TASKLIST)
        assert url == "mock_question_url"
        question_mock.assert_called_once_with(runner, question, question.form, FormRunnerState.TASKLIST)

        question_mock.reset_mock()
        runner.to_url(FormRunnerState.QUESTION, question=second_question)
        question_mock.assert_called_once_with(runner, second_question, question.form, None)

        tasklist_url = runner.to_url(FormRunnerState.TASKLIST)
        assert tasklist_url == "mock_tasklist_url"
        tasklist_mock.assert_called_once_with(runner, question, question.form, None)

        check_answers_url = runner.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
        assert check_answers_url == "mock_check_answers_url"
        check_answers_mock.assert_called_once_with(runner, question, question.form, None)

        check_answers_mock.reset_mock()
        runner.to_url(FormRunnerState.CHECK_YOUR_ANSWERS, form=second_form)
        check_answers_mock.assert_called_once_with(runner, question, second_form, None)

    def test_next_url(self, factories, app):
        question = factories.question.build()
        second_question = factories.question.build(form=question.form)
        submission = factories.submission.build(collection=question.form.section.collection)
        helper = SubmissionHelper(submission)

        question_mock = Mock(side_effect=lambda r, q, f, s: f"mock_question_url_{str(q.id)}")
        check_your_answers_mock = Mock(return_value="mock_check_answers_url")

        class MappedFormRunner(FormRunner):
            url_map = {
                FormRunnerState.QUESTION: question_mock,
                FormRunnerState.CHECK_YOUR_ANSWERS: check_your_answers_mock,
            }

        runner = MappedFormRunner(submission=helper, question=question, source=None)
        assert (
            runner.validate_can_show_question_page()
            and runner.next_url == f"mock_question_url_{str(second_question.id)}"
        )

        end_of_form = MappedFormRunner(submission=helper, question=second_question, source=None)
        assert end_of_form.validate_can_show_question_page() and end_of_form.next_url == "mock_check_answers_url"

    @pytest.mark.parametrize("source", [FormRunnerState.QUESTION, FormRunnerState.CHECK_YOUR_ANSWERS])
    def test_next_url_skips_answered_questions_and_always_goes_to_next_unanswered_question(
        self, factories, app, source
    ):
        question = factories.question.build()
        second_question = factories.question.build(form=question.form)
        third_question = factories.question.build(form=question.form)
        submission = factories.submission.build(
            collection=question.form.section.collection,
            data={
                str(second_question.id): TextSingleLineAnswer("hi").get_value_for_submission(),
            },
        )
        helper = SubmissionHelper(submission)

        question_mock = Mock(side_effect=lambda r, q, f, s: f"mock_question_url_{str(q.id)}")
        check_your_answers_mock = Mock(return_value="mock_check_answers_url")

        class MappedFormRunner(FormRunner):
            url_map = {
                FormRunnerState.QUESTION: question_mock,
                FormRunnerState.CHECK_YOUR_ANSWERS: check_your_answers_mock,
            }

        runner = MappedFormRunner(submission=helper, question=question, source=source)
        runner.validate_can_show_question_page()
        assert runner.next_url == f"mock_question_url_{str(third_question.id)}", (
            "should skip over 2nd question as it has an answer"
        )

        runner = MappedFormRunner(submission=helper, question=second_question, source=source)
        runner.validate_can_show_question_page()
        assert runner.next_url == f"mock_question_url_{str(third_question.id)}"

        runner = MappedFormRunner(submission=helper, question=third_question, source=source)
        runner.validate_can_show_question_page()
        assert runner.next_url == "mock_check_answers_url"

    def test_back_url(self, factories):
        question = factories.question.build()
        second_question = factories.question.build(form=question.form)
        submission = factories.submission.build(collection=question.form.section.collection)
        helper = SubmissionHelper(submission)

        question_mock = Mock(side_effect=lambda r, q, f, s: f"mock_question_url_{str(q.id)}")
        tasklist_mock = Mock(return_value="mock_tasklist_url")

        class MappedFormRunner(FormRunner):
            url_map = {FormRunnerState.QUESTION: question_mock, FormRunnerState.TASKLIST: tasklist_mock}

        runner = MappedFormRunner(submission=helper, question=second_question, source=None)
        assert runner.back_url == f"mock_question_url_{str(question.id)}"

        start_of_form = MappedFormRunner(submission=helper, question=question, source=None)
        assert start_of_form.back_url == "mock_tasklist_url"

    def test_next_back_url_for_group(self, factories):
        q1 = factories.question.build(order=0)
        group = factories.group.build(
            form=q1.form,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
            order=1,
        )
        factories.question.build(parent=group, order=0)
        nested_q3 = factories.question.build(parent=group, order=1)
        factories.question.build(parent=group, order=2)
        q5 = factories.question.build(form=group.form, order=2)
        submission = factories.submission.build(collection=group.form.section.collection)
        helper = SubmissionHelper(submission)

        question_mock = Mock(side_effect=lambda r, q, f, s: f"mock_question_url_{str(q.id)}")
        check_your_answers_mock = Mock(return_value="mock_check_answers_url")

        class MappedFormRunner(FormRunner):
            url_map = {
                FormRunnerState.QUESTION: question_mock,
                FormRunnerState.CHECK_YOUR_ANSWERS: check_your_answers_mock,
            }

        runner = MappedFormRunner(submission=helper, question=nested_q3, source=None)

        # even though we're in the middle of a group of questions, the next question should come after the
        # group as they're all shown on the same page
        assert runner.validate_can_show_question_page() and runner.next_url == f"mock_question_url_{str(q5.id)}"

        # similarly the back question should be the question before the group of same page
        assert runner.validate_can_show_question_page() and runner.back_url == f"mock_question_url_{str(q1.id)}"

    class TestUrlConfig:
        @pytest.mark.parametrize("runner_class", FormRunner.__subclasses__())
        def test_runners_url_map_resolves(self, factories, runner_class):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)
            runner = runner_class(submission=SubmissionHelper(submission), question=question)
            for state in FormRunnerState:
                assert runner.to_url(state) is not None
