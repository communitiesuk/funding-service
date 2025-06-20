import pytest

from app.common.data.types import ExpressionType, QuestionDataType
from app.common.expressions.forms import AddNumberConditionForm
from app.common.expressions.managed import (
    GreaterThan,
    get_managed_expression,
    get_managed_expression_form,
    get_supported_form_questions,
    parse_expression_form,
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

        form = get_managed_expression_form(question)
        assert form == AddNumberConditionForm

    def test_get_managed_expression_form_invalid_question_type(self, factories):
        question = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE)

        with pytest.raises(ValueError) as e:
            get_managed_expression_form(question)

        assert str(e.value) == f"Question type {question.data_type} does not support managed expressions"

    def test_parse_managed_expression_form(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = get_managed_expression_form(question)(value=2000)

        expression = parse_expression_form(question, form)
        assert expression.key == "Greater than"
        assert expression.question_id == question.id
        assert expression.minimum_value == 2000

    def test_parse_managed_expression_from_context(self, factories):
        expression = factories.expression.build(type=ExpressionType.CONDITION)

        expression.context = {"key": "Greater than", "question_id": str(expression.question.id), "minimum_value": 1000}

        managed_expression = get_managed_expression(expression)
        assert isinstance(managed_expression, GreaterThan)
        assert managed_expression.minimum_value == 1000
