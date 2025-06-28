import pytest
from immutabledict import immutabledict

from app.common.data.interfaces.collections import add_question_condition
from app.common.expressions import ExpressionContext, evaluate
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
        question = factories.question.create()
        managed_expression = GreaterThan(minimum_value=3000, question_id=question.id)
        add_question_condition(question, user, managed_expression)

        expr = question.expressions[0]

        assert evaluate(expr, ExpressionContext(immutabledict({question.safe_qid: 500}))) is False
        assert evaluate(expr, ExpressionContext(immutabledict({question.safe_qid: 3000}))) is False
        assert evaluate(expr, ExpressionContext(immutabledict({question.safe_qid: 3001}))) is True
