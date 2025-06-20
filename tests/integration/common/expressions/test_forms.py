from app.common.data.types import ManagedExpressions, QuestionDataType
from app.common.expressions.forms import AddIntegerConditionForm, AddIntegerValidationForm


class TestAddIntegerConditionForm:
    def test_get_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerConditionForm(type=ManagedExpressions.GREATER_THAN.value, value=2000)

        expression = form.get_expression(question)
        assert expression.key == "Greater than"
        assert expression.question_id == question.id
        assert expression.minimum_value == 2000


class TestAddIntegerValidationForm:
    def test_get_greater_than_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerValidationForm(
            type=ManagedExpressions.GREATER_THAN.value, greater_than_value=2000, greater_than_inclusive=False
        )

        expression = form.get_expression(question)
        assert expression.key == "Greater than"
        assert expression.question_id == question.id
        assert expression.minimum_value == 2000

    def test_get_less_than_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerValidationForm(
            type=ManagedExpressions.LESS_THAN.value, less_than_value=2000, less_than_inclusive=False
        )

        expression = form.get_expression(question)
        assert expression.key == "Less than"
        assert expression.question_id == question.id
        assert expression.maximum_value == 2000

    def test_get_between_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerValidationForm(
            type=ManagedExpressions.BETWEEN.value,
            bottom_of_range=10,
            bottom_inclusive=False,
            top_of_range=20,
            top_inclusive=False,
        )

        expression = form.get_expression(question)
        assert expression.key == "Between"
        assert expression.question_id == question.id
        assert expression.minimum_value == 10
        assert expression.minimum_inclusive is False
        assert expression.maximum_value == 20
        assert expression.maximum_inclusive is False
