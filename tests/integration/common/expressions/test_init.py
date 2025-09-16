import datetime
from unittest.mock import PropertyMock

import pytest

from app.common.data.models import Expression
from app.common.data.types import ExpressionType
from app.common.expressions import DisallowedExpression, ExpressionContext, SubmissionContext, evaluate
from app.common.expressions.managed import GreaterThan


class TestExpressionContext:
    def test_layering(self):
        from_form = {"a": 1, "b": 1, "e": 1}
        from_submission = {"a": 2, "c": 2}
        ex = ExpressionContext(
            submission_context=SubmissionContext(form_data=from_form, submission_data=from_submission),
            expression_context={"a": 3, "c": 3, "d": 3},
        )
        assert ex["a"] == 1
        assert ex["b"] == 1
        assert ex["c"] == 2
        assert ex["d"] == 3
        assert ex["e"] == 1

        with pytest.raises(KeyError):
            assert ex["f"]

    def test_get(self):
        from_form = {"a": 1, "b": 1, "e": 1}
        from_submission = {"a": 2, "c": 2}
        ex = ExpressionContext(
            submission_context=SubmissionContext(form_data=from_form, submission_data=from_submission),
            expression_context={"a": 3, "c": 3, "d": 3},
        )
        assert ex.get("a") == 1
        assert ex.get("b") == 1
        assert ex.get("c") == 2
        assert ex.get("d") == 3
        assert ex.get("e") == 1
        assert ex.get("f") is None

    def test_length(self):
        from_form = {"a": 1, "b": 1, "e": 1}
        from_submission = {"a": 2, "c": 2}
        ex = ExpressionContext(
            submission_context=SubmissionContext(form_data=from_form, submission_data=from_submission),
            expression_context={"a": 3, "c": 3, "d": 3},
        )
        assert len(ex) == 5

    def test_contains(self):
        from_form = {"a": 1, "b": 1, "e": 1}
        from_submission = {"a": 2, "c": 2}
        ex = ExpressionContext(
            submission_context=SubmissionContext(form_data=from_form, submission_data=from_submission),
            expression_context={"a": 3, "c": 3, "d": 3},
        )
        assert "a" in ex
        assert "b" in ex
        assert "c" in ex
        assert "d" in ex
        assert "e" in ex
        assert "f" not in ex


class TestEvaluatingManagedExpressions:
    def test_greater_than(self, factories):
        user = factories.user.create()
        q0 = factories.question.create()
        question = factories.question.create(
            form=q0.form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q0.id, minimum_value=3000), user)],
        )

        expr = question.expressions[0]

        assert evaluate(expr, ExpressionContext({q0.safe_qid: 500})) is False
        assert evaluate(expr, ExpressionContext({q0.safe_qid: 3000})) is False
        assert evaluate(expr, ExpressionContext({q0.safe_qid: 3001})) is True


class TestEvaluatingManagedExpressionsWithRequiredFunctions:
    @pytest.mark.parametrize(
        "question_value, expected_result",
        [
            (datetime.date(2023, 12, 1), True),
            (datetime.date(2026, 12, 1), False),
        ],
    )
    def test_managed_expression_with_required_function_allowed_imported(
        self, factories, mocker, question_value, expected_result
    ):
        expr = factories.expression.build(statement="q_123 < date(2024, 1, 1)", type_=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"date": datetime.date},
        )
        assert (
            evaluate(
                expr, ExpressionContext(submission_context=SubmissionContext(submission_data={"q_123": question_value}))
            )
            is expected_result
        )

    @pytest.mark.parametrize(
        "question_value, expected_result",
        [
            (309, True),
            (0, False),
        ],
    )
    def test_managed_expression_with_required_function_allowed_builtin(
        self, factories, mocker, question_value, expected_result
    ):
        expr = factories.expression.build(statement="q_123 > min(1,2)", type_=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"min": min},
        )
        assert (
            evaluate(
                expr, ExpressionContext(submission_context=SubmissionContext(submission_data={"q_123": question_value}))
            )
            is expected_result
        )

    @pytest.mark.parametrize(
        "question_value, expected_result",
        [
            (100, True),
            (5, False),
        ],
    )
    def test_managed_expression_with_required_function_allowed_custom(
        self, factories, mocker, question_value, expected_result
    ):
        def _custom_test_function():
            return 42

        expr = factories.expression.build(statement="q_123 > calculate_result()", type_=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"calculate_result": _custom_test_function},
        )
        assert (
            evaluate(
                expr, ExpressionContext(submission_context=SubmissionContext(submission_data={"q_123": question_value}))
            )
            is expected_result
        )

    def test_managed_expression_with_required_function_builtin_not_present_builtin(self, factories):
        # test with a builtin function that isn't on the allowed list
        expr = factories.expression.build(statement="q_123 > max(1,2)", type_=ExpressionType.VALIDATION)
        # Don't patch the required_functions property, so it returns an empty dict
        with pytest.raises(DisallowedExpression):
            evaluate(expr, ExpressionContext(submission_context=SubmissionContext(submission_data={"q_123": 123})))

    def test_managed_expression_with_required_function_not_present_custom(self, factories):
        def _custom_test_function():
            return 42

        # Test with a custom function that isn't on the allowed list
        expr = factories.expression.build(statement="q_123 > _custom_test_function()", type_=ExpressionType.VALIDATION)
        # Don't patch the required_functions property, so it returns an empty dict
        with pytest.raises(DisallowedExpression):
            evaluate(expr, ExpressionContext(submission_context=SubmissionContext(submission_data={"q_123": 123})))
