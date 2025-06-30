import pytest
from werkzeug.datastructures import MultiDict

from app.common.data.interfaces.collections import add_question_validation
from app.common.data.types import ManagedExpressionsEnum, QuestionDataType
from app.common.expressions.forms import AddIntegerExpressionForm
from app.common.expressions.managed import GreaterThan


class TestAddIntegerValidationForm:
    @pytest.mark.parametrize("greater_than", (-100, 0, 100))
    def test_get_greater_than_expression(self, factories, greater_than):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerExpressionForm(
            formdata=MultiDict(
                dict(
                    type=ManagedExpressionsEnum.GREATER_THAN.value,
                    greater_than_value=str(greater_than),
                    greater_than_inclusive="",
                )
            )
        )

        expression = form.get_expression(question)
        assert expression._key == "Greater than"
        assert expression.question_id == question.id
        assert expression.minimum_value == greater_than

    @pytest.mark.parametrize("less_than", (-100, 0, 100))
    def test_get_less_than_expression(self, factories, less_than):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerExpressionForm(
            formdata=MultiDict(
                dict(
                    type=ManagedExpressionsEnum.LESS_THAN.value, less_than_value=str(less_than), less_than_inclusive=""
                )
            )
        )

        expression = form.get_expression(question)
        assert expression._key == "Less than"
        assert expression.question_id == question.id
        assert expression.maximum_value == less_than

    @pytest.mark.parametrize(
        "minimum_value, maximum_value",
        (
            (0, 100),  # Make sure 0 is accepted for minimum value
            (10, 20),
            (-100, 0),  # Make sure 0 is accepted for maximum value
        ),
    )
    def test_get_between_expression(self, factories, minimum_value, maximum_value):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        form = AddIntegerExpressionForm(
            formdata=MultiDict(
                dict(
                    type=ManagedExpressionsEnum.BETWEEN.value,
                    bottom_of_range=str(minimum_value),
                    bottom_inclusive="",
                    top_of_range=str(maximum_value),
                    top_inclusive="",
                )
            )
        )

        expression = form.get_expression(question)
        assert expression._key == "Between"
        assert expression.question_id == question.id
        assert expression.minimum_value == minimum_value
        assert expression.minimum_inclusive is False
        assert expression.maximum_value == maximum_value
        assert expression.maximum_inclusive is False

    def test_from_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        user = factories.user.build()
        add_question_validation(question, user, GreaterThan(question_id=question.id, minimum_value=10))
        gt_expression = question.validations[0]

        form = AddIntegerExpressionForm.from_expression(gt_expression)
        assert form.greater_than_value.data == 10
        assert form.greater_than_inclusive.data is False
