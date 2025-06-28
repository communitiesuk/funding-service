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
)


class TestInternalEvaluateExpressionWithContext:
    @pytest.mark.parametrize(
        "statement, context, expected_result",
        (
            # ast.UnaryOp
            ("not 1", {}, False),
            # ast.Expr / ast.Constant
            ("1", {}, 1),
            # ast.Name
            ("variable", {"variable": True}, True),
            # ast.BinOp
            ("1 + 1", {}, 2),
            ("1 - 1", {}, 0),
            ("1 * 2", {}, 2),
            ("10 / 2", {}, 5),
            # ast.BoolOp
            ("0 or 1", {}, True),
            ("0 and 1", {}, False),
            # ast.Compare
            ("10 > 1", {}, True),
            ("10 == 1", {}, False),
            ("10 <= 1", {}, False),
            ("True", {}, True),
            ("False", {}, False),
            # ast.Subscript
            ("variable[0]", {"variable": [1, 2, 3]}, 1),
            # ast.Attribute
            ("variable.value", {"variable": Mock(value="potato")}, "potato"),
        ),
    )
    def test_allowed_expressions(self, statement, context, expected_result):
        assert _evaluate_expression_with_context(statement, context) == expected_result

    @pytest.mark.parametrize(
        "statement, context",
        (
            ("import os", {}),
            ("raise Exception", {}),  # ast.Keyword
            ("eval('1')", {}),
            ("input('hi')", {}),
            ("print('hi')", {}),
            ("exec('1')", {}),
            ("compile('1')", {}),
            ("__import__('os')", {}),
            ("getattr()", {}),
            ("setattr()", {}),
            ("delattr()", {}),
            ("hasattr()", {}),
            ("memoryview()", {}),
            ("bytearray()", {}),
            ("open()", {}),
            ("vars()", {}),
            ("dir()", {}),
            ("globals()", {}),
            ("locals()", {}),
            ("a = 1", {}),  # ast.Assign
            ("a += 1", {"a": 1}),  # ast.AugAssign
            ("1 if True else 2", {}),  # ast.IfExp
            ("f'hi'", {}),  # ast.JoinedStr
            ("f'{var}'", {"var": 1}),  # ast.JoinedStr
        ),
    )
    def test_disallowed_expressions(self, statement, context):
        with pytest.raises(DisallowedExpression):
            _evaluate_expression_with_context(statement, context)

    def test_unknown_variable(self):
        with pytest.raises(UndefinedVariableInExpression):
            _evaluate_expression_with_context("blah", {})

    def test_works_with_plain_dicts(self):
        assert _evaluate_expression_with_context("a + 1", {"a": 1}) == 2

    def test_works_with_expression_context(self):
        assert _evaluate_expression_with_context("a + 1", ExpressionContext({"a": 1})) == 2
        assert _evaluate_expression_with_context("a + 1", ExpressionContext({}, {"a": 1})) == 2
        assert _evaluate_expression_with_context("a + 1", ExpressionContext({}, {}, {"a": 1})) == 2


class TestEvaluate:
    def test_ok_with_boolean_result(self):
        assert evaluate(Expression(statement="True is False"), {}) is False

    def test_additional_context(self):
        assert evaluate(Expression(statement="answer == 1"), context=ExpressionContext({"answer": 1})) is True

    def test_raise_on_non_boolean_result(self):
        with pytest.raises(InvalidEvaluationResult):
            evaluate(Expression(statement="1"), context={})
