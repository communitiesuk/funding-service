from unittest.mock import Mock

import pytest

from app.common.data.models import Expression
from app.common.expressions import (
    DisallowedExpression,
    ExpressionContext,
    InvalidEvaluationResult,
    UndefinedVariableInExpression,
    _evaluate_expression_with_context,
    evaluate,
    interpolate,
)


class TestInternalEvaluateExpressionWithContext:
    @pytest.mark.parametrize(
        "expression, expected_result",
        (
            # ast.UnaryOp
            (Expression(statement="not 1"), False),
            # ast.Expr / ast.Constant
            (Expression(statement="1"), 1),
            # ast.Name
            (Expression(statement="variable", context={"variable": True}), True),
            # ast.BinOp
            (Expression(statement="1 + 1"), 2),
            (Expression(statement="1 - 1"), 0),
            (Expression(statement="1 * 2"), 2),
            (Expression(statement="10 / 2"), 5),
            # ast.BoolOp
            (Expression(statement="0 or 1"), True),
            (Expression(statement="0 and 1"), False),
            # ast.Compare
            (Expression(statement="10 > 1"), True),
            (Expression(statement="10 == 1"), False),
            (Expression(statement="10 <= 1"), False),
            (Expression(statement="True"), True),
            (Expression(statement="False"), False),
            # ast.Subscript
            (Expression(statement="variable[0]", context={"variable": [1, 2, 3]}), 1),
            # ast.Attribute
            (
                Expression(statement="variable.value", context={"variable": Mock(value="potato")}),
                "potato",
            ),
        ),
    )
    def test_allowed_expressions(self, expression, expected_result):
        assert _evaluate_expression_with_context(expression) == expected_result

    @pytest.mark.parametrize(
        "expression",
        (
            (Expression(statement="import os")),
            (Expression(statement="raise Exception")),  # ast.Keyword
            (Expression(statement="eval('1')")),
            (Expression(statement="input('hi')")),
            (Expression(statement="print('hi')")),
            (Expression(statement="exec('1')")),
            (Expression(statement="compile('1')")),
            (Expression(statement="__import__('os')")),
            (Expression(statement="getattr()")),
            (Expression(statement="setattr()")),
            (Expression(statement="delattr()")),
            (Expression(statement="hasattr()")),
            (Expression(statement="memoryview()")),
            (Expression(statement="bytearray()")),
            (Expression(statement="open()")),
            (Expression(statement="vars()")),
            (Expression(statement="dir()")),
            (Expression(statement="globals()")),
            (Expression(statement="locals()")),
            (Expression(statement="a = 1")),  # ast.Assign
            (Expression(statement="a += 1", context={"a": 1})),  # ast.AugAssign
            (Expression(statement="1 if True else 2")),  # ast.IfExp
            (Expression(statement="f'hi'")),  # ast.JoinedStr
            (Expression(statement="f'{var}'", context={"var": 1})),  # ast.JoinedStr
        ),
    )
    def test_disallowed_expressions(self, expression):
        with pytest.raises(DisallowedExpression):
            _evaluate_expression_with_context(expression, ExpressionContext())

    def test_unknown_variable(self):
        with pytest.raises(UndefinedVariableInExpression):
            expression = Expression(statement="blah")
            _evaluate_expression_with_context(expression, ExpressionContext())


class TestEvaluate:
    def test_ok_with_boolean_result(self):
        assert evaluate(Expression(statement="True is False"), ExpressionContext()) is False

    def test_additional_context(self):
        assert (
            evaluate(
                Expression(statement="answer == 1"),
                context=ExpressionContext({"answer": 1}),
            )
            is True
        )

    def test_raise_on_non_boolean_result(self):
        with pytest.raises(InvalidEvaluationResult):
            evaluate(Expression(statement="1"), context=ExpressionContext())


class TestInterpolate:
    def test_no_interpolation_patterns(self):
        assert interpolate("This is plain text with no patterns", None) == "This is plain text with no patterns"

    def test_single_integer_interpolation(self):
        assert interpolate("The answer is ((42))", None) == "The answer is 42"

    def test_single_string_interpolation(self):
        assert interpolate("Hello (('world'))", None) == "Hello world"

    def test_multiple_interpolations(self):
        assert interpolate("First: ((10)), Second: (('test'))", None) == "First: 10, Second: test"

    def test_integer_formatting_with_commas(self):
        assert interpolate("Large number: ((1000000))", None) == "Large number: 1000000"

    def test_interpolation_with_context(self):
        assert (
            interpolate("Value: ((value)), Name: ((name))", ExpressionContext({"value": 123, "name": "test"}))
            == "Value: 123, Name: test"
        )

    def test_interpolation_with_expressions(self):
        assert interpolate("Sum: ((x + y))", ExpressionContext({"x": 10, "y": 20})) == "Sum: 30"

    def test_nested_parentheses_in_interpolation(self):
        assert interpolate("First: ((values[0]))", ExpressionContext({"values": [1, 2, 3]})) == "First: 1"

    def test_complex_expression_with_string_result(self):
        assert (
            interpolate("Message: ((first + ' ' + second))", ExpressionContext({"first": "Hello", "second": "World"}))
            == "Message: Hello World"
        )

    def test_zero_integer_formatting(self):
        assert interpolate("Zero: ((0))", None) == "Zero: 0"

    def test_negative_integer_formatting(self):
        assert interpolate("Negative: ((-1234))", None) == "Negative: -1234"

    def test_empty_string_interpolation(self):
        assert interpolate("Empty: ((''))", None) == "Empty: "

    def test_expression_error_propagates(self):
        with pytest.raises(UndefinedVariableInExpression):
            interpolate("Error: ((undefined_variable))", None)

    def test_multiple_patterns_with_mixed_types(self):
        assert (
            interpolate(
                "There are ((count)) ((message)) in total", ExpressionContext({"count": 42, "message": "items"})
            )
            == "There are 42 items in total"
        )

    def test_adjacent_interpolation_patterns(self):
        assert interpolate("((10))((20))", None) == "1020"

    def test_interpolation_with_context_override(self):
        assert (
            interpolate(
                "Value: ((value))", ExpressionContext(submission_data={"value": 100}, expression_context={"value": 200})
            )
            == "Value: 100"
        )
