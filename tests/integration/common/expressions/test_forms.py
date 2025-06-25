from app.common.data.interfaces.collections import add_question_validation
from app.common.data.types import ManagedExpressionsEnum, QuestionDataType
from app.common.expressions.forms import AddIntegerExpressionForm
from app.common.expressions.managed import GreaterThan


class TestAddIntegerValidationForm:
    def test_get_greater_than_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerExpressionForm(
            type=ManagedExpressionsEnum.GREATER_THAN.value, greater_than_value=2000, greater_than_inclusive=False
        )

        expression = form.get_expression(question)
        assert expression._key == "Greater than"
        assert expression.question_id == question.id
        assert expression.minimum_value == 2000

    def test_get_less_than_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerExpressionForm(
            type=ManagedExpressionsEnum.LESS_THAN.value, less_than_value=2000, less_than_inclusive=False
        )

        expression = form.get_expression(question)
        assert expression._key == "Less than"
        assert expression.question_id == question.id
        assert expression.maximum_value == 2000

    def test_get_between_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerExpressionForm(
            type=ManagedExpressionsEnum.BETWEEN.value,
            bottom_of_range=10,
            bottom_inclusive=False,
            top_of_range=20,
            top_inclusive=False,
        )

        expression = form.get_expression(question)
        assert expression._key == "Between"
        assert expression.question_id == question.id
        assert expression.minimum_value == 10
        assert expression.minimum_inclusive is False
        assert expression.maximum_value == 20
        assert expression.maximum_inclusive is False

    def test_from_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        user = factories.user.build()
        add_question_validation(question, user, GreaterThan(question_id=question.id, minimum_value=10))
        gt_expression = question.validations[0]

        form = AddIntegerExpressionForm.from_expression(gt_expression)
        assert form.greater_than_value.data == 10
        assert form.greater_than_inclusive.data is False
