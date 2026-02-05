from datetime import date
from decimal import Decimal
from unittest.mock import Mock, PropertyMock

import pytest
from markupsafe import Markup

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
            # ast.Compare with reference data - references saved as ((safe_qids)) in statement, (()) are ignored
            (Expression(statement="variable1 < ((variable2))", context={"variable1": 2, "variable2": 10}), True),
            (Expression(statement="variable1 >= ((variable2))", context={"variable1": 2, "variable2": 2}), True),
            (
                Expression(
                    statement="((variable1)) >= variable2 > ((variable3))",
                    context={"variable1": 10, "variable2": 3, "variable3": 3},
                ),
                False,
            ),
            (
                Expression(
                    statement="variable1 < ((variable2))",
                    context={"variable1": date(2020, 1, 1), "variable2": date(2021, 1, 1)},
                ),
                True,
            ),
            (
                Expression(
                    statement="((variable1)) < variable2 <= ((variable3))",
                    context={
                        "variable1": date(2020, 1, 1),
                        "variable2": date(2020, 1, 1),
                        "variable3": date(2021, 1, 1),
                    },
                ),
                False,
            ),
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

    def test_decimal_evaluation(self):
        result = evaluate(Expression(statement="value < 0.5"), context=ExpressionContext({"value": Decimal("0.25")}))
        assert result is True
        result = evaluate(Expression(statement="value < 1"), context=ExpressionContext({"value": Decimal("0.25")}))
        assert result is True
        result = evaluate(Expression(statement="value < 1.31"), context=ExpressionContext({"value": Decimal("0.30")}))
        assert result is True
        result = evaluate(Expression(statement="value < 1.3"), context=ExpressionContext({"value": Decimal("1.29")}))
        assert result is True
        result = evaluate(Expression(statement="value <= 1.31"), context=ExpressionContext({"value": Decimal("1.31")}))
        assert result is True

    def test_decimal_evaluation_equality(self, mocker):
        result = evaluate(
            Expression(statement="value1 >= value2"),
            context=ExpressionContext({"value1": Decimal("0.002"), "value2": Decimal("0.001")}),
        )
        assert result is True
        result = evaluate(
            Expression(statement="value1 >= value2"),
            context=ExpressionContext({"value1": Decimal("0.001"), "value2": Decimal("0.001")}),
        )
        assert result is True
        expr = Expression(statement="value >= Decimal('0.001')")
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"Decimal": Decimal},
        )
        result = evaluate(
            expr,
            context=ExpressionContext({"value": Decimal("0.002")}),
        )
        assert result is True
        expr = Expression(statement="value >= Decimal('0.001')")
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"Decimal": Decimal},
        )
        result = evaluate(
            expr,
            context=ExpressionContext({"value": Decimal("0.001")}),
        )
        assert result is True


class TestCustomExpressions:
    def test_custom_expressions_less_than(self):
        assert (
            evaluate(
                Expression(statement="value1 < value2"),
                context=ExpressionContext({"value1": Decimal("0.25"), "value2": Decimal("1.25")}),
            )
            is True
        )
        assert (
            evaluate(
                Expression(statement="value1 < value2"),
                context=ExpressionContext({"value1": Decimal("6"), "value2": Decimal("1.25")}),
            )
            is False
        )

    def test_custom_expressions_greater_than(self):
        assert (
            evaluate(
                Expression(statement="value1 > value2"),
                context=ExpressionContext({"value1": Decimal("0.25"), "value2": Decimal("1.25")}),
            )
            is False
        )
        assert (
            evaluate(
                Expression(statement="value1 > value2"),
                context=ExpressionContext({"value1": Decimal("6"), "value2": Decimal("1.25")}),
            )
            is True
        )

    def test_custom_expressions_add(self):
        assert (
            evaluate(
                Expression(statement="value1 + value2 > 10"),
                context=ExpressionContext({"value1": Decimal("0.25"), "value2": Decimal("1.25")}),
            )
            is False
        )
        assert (
            evaluate(
                Expression(statement="value1 + value2 <= 6.25"),
                context=ExpressionContext({"value1": Decimal("6"), "value2": Decimal("0.25")}),
            )
            is True
        )

    def test_custom_expressions_subtract(self):
        assert (
            evaluate(
                Expression(statement="value1 - value2 > 10"),
                context=ExpressionContext({"value1": Decimal("23"), "value2": Decimal("18.25")}),
            )
            is False
        )
        assert (
            evaluate(
                Expression(statement="value1 - value2 <= 6.25"),
                context=ExpressionContext({"value1": Decimal("6"), "value2": Decimal("0.25")}),
            )
            is True
        )

    def test_custom_expressions_kitchen_sink(self, mocker):
        # TODO this doesn't work - arrays not allowed??
        expr = Expression(statement="value1 - value2 > (value3 * value4)")

        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"sum": sum},
        )
        assert (
            evaluate(
                expr,
                context=ExpressionContext(
                    {
                        "value1": Decimal("23"),
                        "value2": Decimal("18.25"),
                        "value3": Decimal("3"),
                        "value4": Decimal("2"),
                    }
                ),
            )
            is False
        )
        expr = Expression(statement="value1 / value2 > (value3 * value4)/6")

        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"sum": sum},
        )
        assert (
            evaluate(
                expr,
                context=ExpressionContext(
                    {
                        "value1": Decimal("16"),
                        "value2": Decimal("2"),
                        "value3": Decimal("3"),
                        "value4": Decimal("2"),
                    }
                ),
            )
            is True
        )

    def test_custom_sum_function(self):
        # Need to allow sum as a function
        assert (
            evaluate(
                Expression(statement="sum(all_answers_to_q1) > 10"),
                context=ExpressionContext({"all_answers_to_q1": [1, 2, 3, 4]}),
            )
            is False
        )
        assert (
            evaluate(
                Expression(statement="sum(all_answers_to_q1) >= 10"),
                context=ExpressionContext({"all_answers_to_q1": [1, 2, 3, 4]}),
            )
            is True
        )


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

    def test_zero_decimal_formatting(self):
        assert interpolate("Zero: ((0.00))", None) == "Zero: 0.0"

    def test_multiple_decimal_places_formatting(self):
        assert interpolate("Value: ((1234.56789))", None) == "Value: 1234.56789"

    def test_negative_integer_formatting(self):
        assert interpolate("Negative: ((-1234))", None) == "Negative: -1234"

    def test_negative_decimal_formatting(self):
        assert interpolate("Negative: ((-1234.01))", None) == "Negative: -1234.01"

    def test_empty_string_interpolation(self):
        assert interpolate("Empty: ((''))", None) == "Empty: "

    def test_expression_ignores_undefined_variables(self):
        assert interpolate("Error: ((undefined_variable))", None) == "Error: ((undefined_variable))"

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

    def test_interpolation_with_highlighting_disabled_returns_string(self):
        result = interpolate("The answer is ((42))", None, with_interpolation_highlighting=False)
        assert result == "The answer is 42"
        assert isinstance(result, str)
        assert not isinstance(result, Markup)

    def test_interpolation_with_highlighting_enabled_returns_markup(self):
        result = interpolate("The answer is ((42))", None, with_interpolation_highlighting=True)
        assert result == 'The answer is <span class="app-context-aware-editor--valid-reference">42</span>'
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_multiple_substitutions(self):
        result = interpolate(
            "First: ((x)), Second: ((y))", ExpressionContext({"x": 10, "y": 20}), with_interpolation_highlighting=True
        )
        assert result == (
            'First: <span class="app-context-aware-editor--valid-reference">10</span>, '
            'Second: <span class="app-context-aware-editor--valid-reference">20</span>'
        )
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_string_value(self):
        result = interpolate("Hello (('world'))", None, with_interpolation_highlighting=True)
        assert result == 'Hello <span class="app-context-aware-editor--valid-reference">world</span>'
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_escapes_html_script_tag(self):
        """Test that HTML script tags are escaped when highlighting is enabled"""
        malicious_input = "<script>alert('XSS')</script>"
        result = interpolate(
            "Value: ((value))", ExpressionContext({"value": malicious_input}), with_interpolation_highlighting=True
        )
        # Script tag should be escaped
        assert "&lt;script&gt;" in result
        assert "&lt;/script&gt;" in result
        assert "<script>" not in result
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_escapes_html_img_tag(self):
        """Test that HTML img tags with onerror are escaped"""
        malicious_input = '<img src=x onerror="alert(1)">'
        result = interpolate(
            "Value: ((value))", ExpressionContext({"value": malicious_input}), with_interpolation_highlighting=True
        )
        # Should be fully escaped
        assert "&lt;img" in result
        # Quotes should be escaped (either &quot; or &#34;)
        assert "&quot;" in result or "&#34;" in result
        assert '<img src=x onerror="alert(1)">' not in result
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_escapes_html_entities(self):
        """Test that HTML special characters are properly escaped"""
        special_chars = "<>&\"'"
        result = interpolate(
            "Value: ((value))", ExpressionContext({"value": special_chars}), with_interpolation_highlighting=True
        )
        # Should contain escaped versions
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result or "&#" in result
        assert special_chars not in result  # Original unescaped string should not be present
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_escapes_event_handlers(self):
        """Test that inline event handlers are escaped"""
        malicious_input = '" onload="alert(1)'
        result = interpolate(
            "Value: ((value))", ExpressionContext({"value": malicious_input}), with_interpolation_highlighting=True
        )
        # Quotes should be escaped
        assert "&quot;" in result or "&#34;" in result
        assert '" onload="alert(1)' not in result
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_multiple_xss_attempts(self):
        """Test multiple interpolations with XSS attempts"""
        result = interpolate(
            "First: ((x)), Second: ((y))",
            ExpressionContext({"x": "<script>alert(1)</script>", "y": "<img src=x onerror=alert(2)>"}),
            with_interpolation_highlighting=True,
        )
        # Both should be escaped
        assert "&lt;script&gt;" in result
        assert "&lt;img" in result
        assert "<script>" not in result
        assert "<img src=x onerror=alert(2)>" not in result
        assert isinstance(result, Markup)

    def test_interpolation_without_highlighting_returns_plain_string_with_html(self):
        """Test that without highlighting, HTML is returned as plain string (will be auto-escaped by Jinja)"""
        malicious_input = "<script>alert('XSS')</script>"
        result = interpolate(
            "Value: ((value))", ExpressionContext({"value": malicious_input}), with_interpolation_highlighting=False
        )
        # Should return plain string containing the HTML (Jinja will escape it)
        assert result == "Value: <script>alert('XSS')</script>"
        assert isinstance(result, str)
        assert not isinstance(result, Markup)

    def test_interpolation_with_highlighting_safe_content_unchanged(self):
        """Test that safe content is not over-escaped"""
        safe_input = "Hello World 123"
        result = interpolate(
            "Value: ((value))", ExpressionContext({"value": safe_input}), with_interpolation_highlighting=True
        )
        assert "Hello World 123" in result
        assert "&lt;" not in result  # No unnecessary escaping
        assert isinstance(result, Markup)

    def test_interpolate_spits_unknown_references_back_out_without_highlighting(self):
        result = interpolate("Value: ((value))", ExpressionContext({}), with_interpolation_highlighting=True)
        assert "Value: ((value))" in result
        assert isinstance(result, Markup)
