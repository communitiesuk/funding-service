from app.common.data.types import QuestionDataType
from app.common.expressions.forms import AddIntegerConditionForm
from app.common.expressions.helpers import (
    get_managed_condition_form,
    get_supported_form_questions,
)


class TestManagedExpressions:
    def test_get_supported_form_questions_filters_question_types(self, factories):
        form = factories.form.build()
        factories.question.build_batch(3, data_type=QuestionDataType.TEXT_SINGLE_LINE, form=form)
        only_supported_target = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)
        question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        supported_questions = get_supported_form_questions(question)
        assert len(supported_questions) == 1
        assert supported_questions[0].id == only_supported_target.id

    def test_get_supported_form_questions_filters_out_the_current_question(self, factories):
        form = factories.form.build()
        valid_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        assert get_supported_form_questions(valid_question) == []

        second_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        # make sure the original question under test does show up in the correct circumstances
        assert get_supported_form_questions(second_question) == [valid_question]
        assert get_supported_form_questions(valid_question) == [second_question]

    def test_get_managed_expression_form_valid_question_type(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)

        form = get_managed_condition_form(question)
        assert form == AddIntegerConditionForm

    def test_get_managed_expression_form_invalid_question_type(self, factories):
        question = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE)

        assert get_managed_condition_form(question)() is None
