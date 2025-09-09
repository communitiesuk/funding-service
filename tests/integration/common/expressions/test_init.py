import datetime
from unittest.mock import PropertyMock

import pytest
from immutabledict import immutabledict

from app.common.data.models import Expression
from app.common.data.types import ExpressionType
from app.common.expressions import DisallowedExpression, ExpressionContext, evaluate
from app.common.expressions.managed import GreaterThan


class TestExpressionContext:
    def test_layering(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert ex["a"] == 1
        assert ex["b"] == 1
        assert ex["c"] == 2
        assert ex["d"] == 3
        assert ex["e"] == 1

        with pytest.raises(KeyError):
            assert ex["f"]

    def test_iteration(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert [k for k in ex] == ["a", "b", "e", "c", "d"]

    def test_get(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert ex.get("a") == 1
        assert ex.get("b") == 1
        assert ex.get("c") == 2
        assert ex.get("d") == 3
        assert ex.get("e") == 1
        assert ex.get("f") is None

    def test_length(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert len(ex) == 5

    def test_contains(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert "a" in ex
        assert "b" in ex
        assert "c" in ex
        assert "d" in ex
        assert "e" in ex
        assert "f" not in ex

    def test_keys(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert list(ex.keys()) == ["a", "b", "e", "c", "d"]

    def test_values(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert ex.values() == [1, 1, 1, 2, 3]

    def test_items(self):
        ex = ExpressionContext(
            from_form=immutabledict({"a": 1, "b": 1, "e": 1}),
            from_submission=immutabledict({"a": 2, "c": 2}),
            from_expression=immutabledict({"a": 3, "c": 3, "d": 3}),
        )
        assert ex.items() == [("a", 1), ("b", 1), ("e", 1), ("c", 2), ("d", 3)]


class TestEvaluatingManagedExpressions:
    def test_greater_than(self, factories):
        user = factories.user.create()
        q0 = factories.question.create()
        question = factories.question.create(
            form=q0.form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q0.id, minimum_value=3000), user)],
        )

        expr = question.expressions[0]

        assert evaluate(expr, ExpressionContext(immutabledict({q0.safe_qid: 500}))) is False
        assert evaluate(expr, ExpressionContext(immutabledict({q0.safe_qid: 3000}))) is False
        assert evaluate(expr, ExpressionContext(immutabledict({q0.safe_qid: 3001}))) is True


class TestEvaluatingManagedExpressionsWithRequiredFunctions:
    def test_managed_expression_with_custom_required_function_true(self, factories, mocker):
        expr = factories.expression.build(statement="value < date(2025, 1, 1)", type=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"date": datetime.date},
        )
        assert evaluate(expr, ExpressionContext(from_submission={"value": datetime.date(2024, 1, 1)})) is True

    def test_managed_expression_with_custom_required_function_false(self, factories):
        expr = factories.expression.build(statement="value > date(2025, 1, 1)", type=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"date": datetime.date},
        )
        assert evaluate(expr, ExpressionContext(from_submission={"value": datetime.date(2024, 1, 1)})) is True

    def test_managed_expression_with_builtin_required_function(self, factories):
        expr = factories.expression.build(statement="value >= min(1, 2)", type=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"date": datetime.date},
        )
        assert evaluate(expr, ExpressionContext(from_submission={"value": 5})) is True

    def test_managed_expression_with_required_function_not_present(self, factories):
        expr = factories.expression.build(statement="value < date(2025, 1, 1)", type=ExpressionType.VALIDATION)

        # Test with a custom function we haven't added to required_functions
        with pytest.raises(DisallowedExpression):
            evaluate(Expression.from_managed(expr, created_by=factories.user.build()))

        # Test with a builtin function that isn't on the allowed list
        with pytest.raises(DisallowedExpression):
            evaluate(Expression.from_managed(expr, created_by=factories.user.build()))
