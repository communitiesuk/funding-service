from datetime import date
from decimal import Decimal
from unittest.mock import Mock, PropertyMock

import pytest
from markupsafe import Markup

from app.common.data.models import Expression
from app.common.expressions import (
    DisallowedExpression,
    EvaluationStatement,
    ExpressionContext,
    InterpolationStatement,
    InvalidEvaluationResult,
    UndefinedFunctionInExpression,
    UndefinedOperatorInExpression,
    UndefinedVariableInExpression,
    _evaluate_expression_with_context,
    evaluate,
    get_restricted_evaluator,
    interpolate,
)


class TestInternalEvaluateExpressionWithContext:
    @pytest.mark.parametrize(
        "expression, expected_result",
        (
            # ast.Expr / ast.Constant
            (Expression(statement=EvaluationStatement("1")), 1),
            # ast.Name
            (Expression(statement=EvaluationStatement("variable"), context={"variable": True}), True),
            # ast.BinOp
            (Expression(statement=EvaluationStatement("1 + 1")), 2),
            (Expression(statement=EvaluationStatement("1 - 1")), 0),
            (Expression(statement=EvaluationStatement("1 * 2")), 2),
            (Expression(statement=EvaluationStatement("10 / 2")), 5),
            # ast.Compare
            (Expression(statement=EvaluationStatement("10 > 1")), True),
            (Expression(statement=EvaluationStatement("10 == 1")), False),
            (Expression(statement=EvaluationStatement("10 <= 1")), False),
            (Expression(statement=EvaluationStatement("True")), True),
            (Expression(statement=EvaluationStatement("False")), False),
            # ast.Compare with reference data - references saved as ((safe_qids)) in statement, (()) are ignored
            (
                Expression(
                    statement=EvaluationStatement("variable1 < ((variable2))"),
                    context={"variable1": 2, "variable2": 10},
                ),
                True,
            ),
            (
                Expression(
                    statement=EvaluationStatement("variable1 >= ((variable2))"),
                    context={"variable1": 2, "variable2": 2},
                ),
                True,
            ),
            (
                Expression(
                    statement=EvaluationStatement("((variable1)) >= variable2 > ((variable3))"),
                    context={"variable1": 10, "variable2": 3, "variable3": 3},
                ),
                False,
            ),
            (
                Expression(
                    statement=EvaluationStatement("variable1 < ((variable2))"),
                    context={"variable1": date(2020, 1, 1), "variable2": date(2021, 1, 1)},
                ),
                True,
            ),
            (
                Expression(
                    statement=EvaluationStatement("((variable1)) < variable2 <= ((variable3))"),
                    context={
                        "variable1": date(2020, 1, 1),
                        "variable2": date(2020, 1, 1),
                        "variable3": date(2021, 1, 1),
                    },
                ),
                False,
            ),
            # ast.Subscript
            (Expression(statement=EvaluationStatement("variable[0]"), context={"variable": [1, 2, 3]}), 1),
            # ast.Attribute
            (
                Expression(statement=EvaluationStatement("variable.value"), context={"variable": Mock(value="potato")}),
                "potato",
            ),
            (Expression(statement=EvaluationStatement("1 in number_list"), context={"number_list": [1, 2, 3]}), True),
            (Expression(statement=EvaluationStatement("a is True"), context={"a": True}), True),
        ),
    )
    def test_allowed_expressions(self, expression, expected_result):
        assert _evaluate_expression_with_context(expression.statement, expression.context) == expected_result

    @pytest.mark.parametrize(
        "expression",
        (
            (Expression(statement=EvaluationStatement("eval('1')"))),
            (Expression(statement=EvaluationStatement("input('hi')"))),
            (Expression(statement=EvaluationStatement("print('hi')"))),
            (Expression(statement=EvaluationStatement("exec('1')"))),
            (Expression(statement=EvaluationStatement("compile('1')"))),
            (Expression(statement=EvaluationStatement("__import__('os')"))),
            (Expression(statement=EvaluationStatement("getattr()"))),
            (Expression(statement=EvaluationStatement("setattr()"))),
            (Expression(statement=EvaluationStatement("delattr()"))),
            (Expression(statement=EvaluationStatement("hasattr()"))),
            (Expression(statement=EvaluationStatement("memoryview()"))),
            (Expression(statement=EvaluationStatement("bytearray()"))),
            (Expression(statement=EvaluationStatement("open()"))),
            (Expression(statement=EvaluationStatement("vars()"))),
            (Expression(statement=EvaluationStatement("dir()"))),
            (Expression(statement=EvaluationStatement("globals()"))),
            (Expression(statement=EvaluationStatement("locals()"))),
        ),
    )
    def test_function_not_defined(self, expression):
        with pytest.raises(UndefinedFunctionInExpression):
            _evaluate_expression_with_context(expression.statement, ExpressionContext())

    @pytest.mark.parametrize(
        "expression",
        (
            (Expression(statement=EvaluationStatement("import os"))),
            (Expression(statement=EvaluationStatement("raise Exception"))),  # ast.Keyword
            (Expression(statement=EvaluationStatement("a = 1"))),  # ast.Assign
            (Expression(statement=EvaluationStatement("a += 1"), context={"a": 1})),  # ast.AugAssign
            (Expression(statement=EvaluationStatement("1 if True else 2"))),  # ast.IfExp
            (Expression(statement=EvaluationStatement("f'hi'"))),  # ast.JoinedStr
            (Expression(statement=EvaluationStatement("f'{var}'"), context={"var": 1})),  # ast.JoinedStr
            # ast.BoolOp
            (Expression(statement=EvaluationStatement("0 or 1"))),
            (Expression(statement=EvaluationStatement("0 and 1"))),
            (Expression(statement=EvaluationStatement("True is not False"))),
        ),
    )
    def test_disallowed_expressions(self, expression):
        with pytest.raises(DisallowedExpression):
            _evaluate_expression_with_context(expression.statement, ExpressionContext())

    @pytest.mark.parametrize(
        "expression",
        [
            (Expression(statement=EvaluationStatement("2**3"))),  # ast.Pow
            (Expression(statement=EvaluationStatement("2>>3"))),  # ast.RShift
            (Expression(statement=EvaluationStatement("2<<3"))),  # ast.LShift
            (Expression(statement=EvaluationStatement("2^3"))),  # ast.BitXor
            (Expression(statement=EvaluationStatement("2|3"))),  # ast.BitOr
            (Expression(statement=EvaluationStatement("2&3"))),  # ast.BitAnd
            (Expression(statement=EvaluationStatement("not 1"))),  # ast.UnaryOp
            (Expression(statement=EvaluationStatement("~3"))),  # ast.Invert
        ],
    )
    def test_operator_not_defined(self, expression):
        with pytest.raises(UndefinedOperatorInExpression):
            _evaluate_expression_with_context(expression.statement, ExpressionContext())

    def test_unknown_variable(self):
        with pytest.raises(UndefinedVariableInExpression):
            expression = Expression(statement=EvaluationStatement("blah"))
            _evaluate_expression_with_context(expression.statement, ExpressionContext())


class TestEvaluate:
    def test_additional_context(self):
        assert (
            evaluate(
                Expression(statement=EvaluationStatement("answer == 1")),
                context=ExpressionContext({"answer": 1}),
            )
            is True
        )

    def test_raise_on_non_boolean_result(self):
        with pytest.raises(InvalidEvaluationResult):
            evaluate(Expression(statement=EvaluationStatement("1")), context=ExpressionContext())

    def test_decimal_evaluation(self):
        result = evaluate(
            Expression(statement=EvaluationStatement("value < 0.5")),
            context=ExpressionContext({"value": Decimal("0.25")}),
        )
        assert result is True
        result = evaluate(
            Expression(statement=EvaluationStatement("value < 1")),
            context=ExpressionContext({"value": Decimal("0.25")}),
        )
        assert result is True
        result = evaluate(
            Expression(statement=EvaluationStatement("value < 1.31")),
            context=ExpressionContext({"value": Decimal("0.30")}),
        )
        assert result is True
        result = evaluate(
            Expression(statement=EvaluationStatement("value < 1.3")),
            context=ExpressionContext({"value": Decimal("1.29")}),
        )
        assert result is True
        result = evaluate(
            Expression(statement=EvaluationStatement("value <= 1.31")),
            context=ExpressionContext({"value": Decimal("1.31")}),
        )
        assert result is True

    def test_inline_decimal_evaluation(self):
        result = evaluate(
            Expression(statement="value * 1.1 < 10"), context=ExpressionContext({"value": Decimal("4.1")})
        )
        assert result is True
        result = evaluate(
            Expression(statement="1.1 * value < 10"), context=ExpressionContext({"value": Decimal("4.1")})
        )
        assert result is True
        result = evaluate(
            Expression(statement="value1 < 1.2*value2"),
            context=ExpressionContext({"value1": Decimal("4.1"), "value2": 4}),
        )
        assert result is True
        result = evaluate(
            Expression(statement="value1 / 1.1 * 3.4 > 1.2*value2"),
            context=ExpressionContext({"value1": Decimal("0.9"), "value2": 5}),
        )
        assert result is False

        assert (
            evaluate(Expression(statement="value1 + 1.2 == 2.2"), context=ExpressionContext({"value1": Decimal("1.0")}))
            is True
        )
        assert evaluate(Expression(statement="value1 + 1.2 == 2.2"), context=ExpressionContext({"value1": 1})) is True
        assert (
            evaluate(Expression(statement="1.0 + 1.2 == value1"), context=ExpressionContext({"value1": Decimal("2.2")}))
            is True
        )

    def test_eval_returns_decimal(self):
        # During evaluation, we use decimal rather than floats for any literal floats in a statement
        # This test confirms that we are actually using decimals everywhere, not floats
        # If anything changes this to make the test fail, you will see an error as follows:
        #  assert Decimal('2.199999999999999955591079015') == Decimal('2.2') because it is trying to use a float
        # instead of a decmial
        evaluator = get_restricted_evaluator(names={}, required_functions={})
        result = evaluator.eval("1.2+1")
        assert result == Decimal("2.2")

        evaluator = get_restricted_evaluator(names={"value1": Decimal("1.2")}, required_functions={})
        result = evaluator.eval("value1+1")
        assert result == Decimal("2.2")

        evaluator = get_restricted_evaluator(names={"value1": 1}, required_functions={})
        result = evaluator.eval("value1+1.2")
        assert result == Decimal("2.2")

    def test_decimal_evaluation_equality(self, mocker):
        result = evaluate(
            Expression(statement=EvaluationStatement("value1 >= value2")),
            context=ExpressionContext({"value1": Decimal("0.002"), "value2": Decimal("0.001")}),
        )
        assert result is True
        result = evaluate(
            Expression(statement=EvaluationStatement("value1 >= value2")),
            context=ExpressionContext({"value1": Decimal("0.001"), "value2": Decimal("0.001")}),
        )
        assert result is True
        expr = Expression(statement=EvaluationStatement("value >= Decimal('0.001')"))
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
        expr = Expression(statement=EvaluationStatement("value >= Decimal('0.001')"))
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


class TestInterpolate:
    def test_no_interpolation_patterns(self):
        assert (
            interpolate(InterpolationStatement("This is plain text with no patterns"), None)
            == "This is plain text with no patterns"
        )

    def test_single_integer_interpolation(self):
        assert interpolate(InterpolationStatement("The answer is ((42))"), None) == "The answer is 42"

    def test_single_string_interpolation(self):
        assert interpolate(InterpolationStatement("Hello (('world'))"), None) == "Hello world"

    def test_multiple_interpolations(self):
        assert (
            interpolate(InterpolationStatement("First: ((10)), Second: (('test'))"), None) == "First: 10, Second: test"
        )

    def test_integer_formatting_with_commas(self):
        assert interpolate(InterpolationStatement("Large number: ((1000000))"), None) == "Large number: 1000000"

    def test_interpolation_with_context(self):
        assert (
            interpolate(
                InterpolationStatement("Value: ((value)), Name: ((name))"),
                ExpressionContext({"value": 123, "name": "test"}),
            )
            == "Value: 123, Name: test"
        )

    def test_interpolation_with_expressions(self):
        assert interpolate(InterpolationStatement("Sum: ((x + y))"), ExpressionContext({"x": 10, "y": 20})) == "Sum: 30"

    def test_nested_parentheses_in_interpolation(self):
        assert (
            interpolate(InterpolationStatement("First: ((values[0]))"), ExpressionContext({"values": [1, 2, 3]}))
            == "First: 1"
        )

    def test_complex_expression_with_string_result(self):
        assert (
            interpolate(
                InterpolationStatement("Message: ((first + ' ' + second))"),
                ExpressionContext({"first": "Hello", "second": "World"}),
            )
            == "Message: Hello World"
        )

    def test_zero_integer_formatting(self):
        assert interpolate(InterpolationStatement("Zero: ((0))"), None) == "Zero: 0"

    def test_zero_decimal_formatting(self):
        assert interpolate(InterpolationStatement("Zero: ((0.00))"), None) == "Zero: 0.0"

    def test_multiple_decimal_places_formatting(self):
        assert interpolate(InterpolationStatement("Value: ((1234.56789))"), None) == "Value: 1234.56789"

    def test_negative_integer_formatting(self):
        assert interpolate(InterpolationStatement("Negative: ((-1234))"), None) == "Negative: -1234"

    def test_negative_decimal_formatting(self):
        assert interpolate(InterpolationStatement("Negative: ((-1234.01))"), None) == "Negative: -1234.01"

    def test_empty_string_interpolation(self):
        assert interpolate(InterpolationStatement("Empty: ((''))"), None) == "Empty: "

    def test_expression_ignores_undefined_variables(self):
        assert (
            interpolate(InterpolationStatement("Error: ((undefined_variable))"), None)
            == "Error: ((undefined_variable))"
        )

    def test_multiple_patterns_with_mixed_types(self):
        assert (
            interpolate(
                InterpolationStatement("There are ((count)) ((message)) in total"),
                ExpressionContext({"count": 42, "message": "items"}),
            )
            == "There are 42 items in total"
        )

    def test_adjacent_interpolation_patterns(self):
        assert interpolate(InterpolationStatement("((10))((20))"), None) == "1020"

    def test_interpolation_with_context_override(self):
        assert (
            interpolate(
                InterpolationStatement("Value: ((value))"),
                ExpressionContext(submission_data={"value": 100}, expression_context={"value": 200}),
            )
            == "Value: 100"
        )

    def test_interpolation_with_highlighting_disabled_returns_string(self):
        result = interpolate(
            InterpolationStatement("The answer is ((42))"), None, with_interpolation_highlighting=False
        )
        assert result == "The answer is 42"
        assert isinstance(result, str)
        assert not isinstance(result, Markup)

    def test_interpolation_with_highlighting_enabled_returns_markup(self):
        result = interpolate(InterpolationStatement("The answer is ((42))"), None, with_interpolation_highlighting=True)
        assert result == 'The answer is <span class="app-context-aware-editor--valid-reference">42</span>'
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_multiple_substitutions(self):
        result = interpolate(
            InterpolationStatement("First: ((x)), Second: ((y))"),
            ExpressionContext({"x": 10, "y": 20}),
            with_interpolation_highlighting=True,
        )
        assert result == (
            'First: <span class="app-context-aware-editor--valid-reference">10</span>, '
            'Second: <span class="app-context-aware-editor--valid-reference">20</span>'
        )
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_string_value(self):
        result = interpolate(InterpolationStatement("Hello (('world'))"), None, with_interpolation_highlighting=True)
        assert result == 'Hello <span class="app-context-aware-editor--valid-reference">world</span>'
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_escapes_html_script_tag(self):
        """Test that HTML script tags are escaped when highlighting is enabled"""
        malicious_input = "<script>alert('XSS')</script>"
        result = interpolate(
            InterpolationStatement("Value: ((value))"),
            ExpressionContext({"value": malicious_input}),
            with_interpolation_highlighting=True,
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
            InterpolationStatement("Value: ((value))"),
            ExpressionContext({"value": malicious_input}),
            with_interpolation_highlighting=True,
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
            InterpolationStatement("Value: ((value))"),
            ExpressionContext({"value": special_chars}),
            with_interpolation_highlighting=True,
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
            InterpolationStatement("Value: ((value))"),
            ExpressionContext({"value": malicious_input}),
            with_interpolation_highlighting=True,
        )
        # Quotes should be escaped
        assert "&quot;" in result or "&#34;" in result
        assert '" onload="alert(1)' not in result
        assert isinstance(result, Markup)

    def test_interpolation_with_highlighting_multiple_xss_attempts(self):
        """Test multiple interpolations with XSS attempts"""
        result = interpolate(
            InterpolationStatement("First: ((x)), Second: ((y))"),
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
            InterpolationStatement("Value: ((value))"),
            ExpressionContext({"value": malicious_input}),
            with_interpolation_highlighting=False,
        )
        # Should return plain string containing the HTML (Jinja will escape it)
        assert result == "Value: <script>alert('XSS')</script>"
        assert isinstance(result, str)
        assert not isinstance(result, Markup)

    def test_interpolation_with_highlighting_safe_content_unchanged(self):
        """Test that safe content is not over-escaped"""
        safe_input = "Hello World 123"
        result = interpolate(
            InterpolationStatement("Value: ((value))"),
            ExpressionContext({"value": safe_input}),
            with_interpolation_highlighting=True,
        )
        assert "Hello World 123" in result
        assert "&lt;" not in result  # No unnecessary escaping
        assert isinstance(result, Markup)

    def test_interpolate_spits_unknown_references_back_out_without_highlighting(self):
        result = interpolate(
            InterpolationStatement("Value: ((value))"), ExpressionContext({}), with_interpolation_highlighting=True
        )
        assert "Value: ((value))" in result
        assert isinstance(result, Markup)
