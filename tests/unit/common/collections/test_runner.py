from unittest.mock import Mock

import pytest

from app.common.collections.runner import AGFFormRunner, DGFFormRunner, FormRunner
from app.common.data.types import FormRunnerState, QuestionDataType
from app.common.helpers.collections import SubmissionHelper, TextSingleLine


class TestFormRunner:
    def test_form_runner_loads_and_sets_context(self, factories):
        question = factories.question.build()
        submission = factories.submission.build(collection=question.form.section.collection)
        helper = SubmissionHelper(submission)

        question_state_context = FormRunner(submission=helper, question=question, source=None)
        assert question_state_context.question == question
        assert question_state_context.form == question.form
        assert question_state_context.question_form is not None

        check_your_answers_context = FormRunner(submission=helper, form=question.form, source=None)
        assert check_your_answers_context.question is None
        assert check_your_answers_context.form == question.form
        assert check_your_answers_context.check_your_answers_form is not None

        tasklist_context = FormRunner(submission=helper, source=None)
        assert tasklist_context.question is None
        assert tasklist_context.form is None
        assert tasklist_context.tasklist_form is not None

    def test_form_runner_correctly_configures_dynamic_question_form(self, factories):
        question = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        submission = factories.submission.build(
            collection=question.form.section.collection, data={str(question.id): TextSingleLine("An answer").root}
        )
        helper = SubmissionHelper(submission)

        runner = FormRunner(submission=helper, question=question, source=None)
        assert runner.question_form.get_question_field(question) is not None
        assert runner.question_form.get_answer_to_question(question) == "An answer"

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

    def test_next_url(self, factories):
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

    class TestUrlConfig:
        @pytest.mark.parametrize("runner_class", (DGFFormRunner, AGFFormRunner))
        def test_runners_url_map_resolves(self, factories, runner_class):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)
            runner = runner_class(submission=SubmissionHelper(submission), question=question)
            for state in FormRunnerState:
                assert runner.to_url(state) is not None
