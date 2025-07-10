# TODO: write some
from werkzeug.datastructures import MultiDict

from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.expressions.forms import build_managed_expression_form
from app.common.expressions.managed import Between


class TestBuildManagedExpressionForm:
    # Not intended to be an exhaustive check against all question data types, but to prove that fundamentally the
    # system/framework is capable.

    def test_integer_data_type(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        _FormClass = build_managed_expression_form(ExpressionType.CONDITION, question)
        assert _FormClass
        form = _FormClass()

        assert form.type.choices == [
            (ManagedExpressionsEnum.GREATER_THAN, ManagedExpressionsEnum.GREATER_THAN),
            (ManagedExpressionsEnum.LESS_THAN, ManagedExpressionsEnum.LESS_THAN),
            (ManagedExpressionsEnum.BETWEEN, ManagedExpressionsEnum.BETWEEN),
        ]

    def test_recognises_invalid_data_for_a_managed_expression(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)
        _FormClass = build_managed_expression_form(ExpressionType.CONDITION, question)
        assert _FormClass
        form = _FormClass(
            formdata=MultiDict(
                {
                    "type": "Between",
                    "between_bottom_of_range": "",
                    "between_bottom_inclusive": "",
                    "between_top_of_range": "",
                    "between_top_inclusive": "",
                }
            )
        )
        assert form.validate() is False
        assert form.errors == {
            "between_bottom_of_range": [
                "Enter the minimum value allowed for this question",
            ],
            "between_top_of_range": [
                "Enter the maximum value allowed for this question",
            ],
        }

    def test_can_build_a_managed_expression_from_valid_data(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)

        _FormClass = build_managed_expression_form(ExpressionType.CONDITION, question)
        assert _FormClass
        form = _FormClass(
            formdata=MultiDict(
                {
                    "type": "Between",
                    "between_bottom_of_range": "0",
                    "between_bottom_inclusive": "",
                    "between_top_of_range": "100",
                    "between_top_inclusive": "1",
                }
            )
        )
        assert form.validate()
        expression: Between = form.get_expression(question)
        assert expression.name == "Between"
        assert expression.minimum_value == 0
        assert expression.minimum_inclusive is False
        assert expression.maximum_value == 100
        assert expression.maximum_inclusive is True
