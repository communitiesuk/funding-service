import datetime
import uuid
from unittest.mock import PropertyMock

import pytest

from app.common.data.models import Expression
from app.common.data.types import ExpressionType, QuestionDataType
from app.common.expressions import DisallowedExpression, ExpressionContext, evaluate
from app.common.expressions.managed import BetweenDates, GreaterThan
from app.common.helpers.collections import SubmissionHelper


class TestExpressionContext:
    def test_layering(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        assert ex["a"] == 1
        assert ex["b"] == 1
        assert ex["c"] == 2
        assert ex["d"] == 2
        assert ex["e"] == 1

        with pytest.raises(KeyError):
            assert ex["f"]

    def test_get(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        assert ex.get("a") == 1
        assert ex.get("b") == 1
        assert ex.get("c") == 2
        assert ex.get("d") == 2
        assert ex.get("e") == 1
        assert ex.get("f") is None

    def test_length(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        assert len(ex) == 5

    def test_contains(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
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

    @pytest.mark.parametrize(
        "value, expected_result",
        (
            (500, False),
            (3000, False),
            (3001, True),
        ),
    )
    def test_expression_with_numerical_reference_data(self, factories, value, expected_result):
        user = factories.user.create()
        q0 = factories.question.create(data_type=QuestionDataType.INTEGER)
        qid = uuid.uuid4()
        q1 = factories.question.create(
            id=qid,
            form=q0.form,
            data_type=QuestionDataType.INTEGER,
            expressions=[
                Expression.from_managed(
                    GreaterThan(question_id=qid, minimum_value=None, minimum_expression=f"(({q0.safe_qid}))"), user
                )  # Double brackets should be ignored by the evaluation engine
            ],
        )

        expr = q1.expressions[0]

        assert evaluate(expr, ExpressionContext({q0.safe_qid: 3000, q1.safe_qid: value})) is expected_result

    @pytest.mark.parametrize(
        "value, expected_result",
        (
            (datetime.date(2020, 1, 1), False),
            (datetime.date(2025, 1, 1), False),
            (datetime.date(2023, 1, 1), True),
        ),
    )
    def test_expression_with_date_reference_data(self, factories, value, expected_result):
        user = factories.user.create()
        form = factories.form.create()
        q0, q1 = factories.question.create_batch(2, form=form, data_type=QuestionDataType.DATE)

        qid = uuid.uuid4()
        q2 = factories.question.create(
            id=qid,
            form=q0.form,
            expressions=[
                Expression.from_managed(
                    BetweenDates(
                        question_id=qid,
                        earliest_value=None,
                        latest_value=None,
                        earliest_expression=f"(({q0.safe_qid}))",
                        latest_expression=f"(({q1.safe_qid}))",
                    ),
                    user,
                )  # Double brackets should be ignored by the evaluation engine
            ],
        )

        expr = q2.expressions[0]

        assert (
            evaluate(
                expr,
                ExpressionContext(
                    {
                        q0.safe_qid: datetime.date(2020, 1, 1),
                        q1.safe_qid: datetime.date(2025, 1, 1),
                        q2.safe_qid: value,
                    }
                ),
            )
            is expected_result
        )


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
        assert evaluate(expr, ExpressionContext(submission_data={"q_123": question_value})) is expected_result

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
        assert evaluate(expr, ExpressionContext(submission_data={"q_123": question_value})) is expected_result

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
        assert evaluate(expr, ExpressionContext(submission_data={"q_123": question_value})) is expected_result

    def test_managed_expression_with_required_function_builtin_not_present_builtin(self, factories):
        # test with a builtin function that isn't on the allowed list
        expr = factories.expression.build(statement="q_123 > max(1,2)", type_=ExpressionType.VALIDATION)
        # Don't patch the required_functions property, so it returns an empty dict
        with pytest.raises(DisallowedExpression):
            evaluate(expr, ExpressionContext(submission_data={"q_123": 123}))

    def test_managed_expression_with_required_function_not_present_custom(self, factories):
        def _custom_test_function():
            return 42

        # Test with a custom function that isn't on the allowed list
        expr = factories.expression.build(statement="q_123 > _custom_test_function()", type_=ExpressionType.VALIDATION)
        # Don't patch the required_functions property, so it returns an empty dict
        with pytest.raises(DisallowedExpression):
            evaluate(expr, ExpressionContext(submission_data={"q_123": 123}))


class TestExtendingWithAddAnotherContext:
    def test_extending_with_add_another_context(self, factories):
        group = factories.group.build(add_another=True)
        q1 = factories.question.build(parent=group)
        q2 = factories.question.build(parent=group)
        submission = factories.submission.build(collection=group.form.collection)
        submission.data = {
            str(group.id): [
                {str(q1.id): "v0", str(q2.id): "e0"},
                {str(q1.id): "v1", str(q2.id): "e1"},
                {str(q1.id): "v2"},
            ]
        }

        context = ExpressionContext.build_expression_context(
            collection=group.form.collection,
            submission_helper=SubmissionHelper(submission=submission),
            mode="evaluation",
        )
        assert context.get(q1.safe_qid_all_answers) == ["v0", "v1", "v2"]

        context = context.with_add_another_context(component=q1, add_another_index=1)
        assert context.get(q1.safe_qid) == "v1"
        assert context.get(q2.safe_qid) == "e1"

    def test_extending_with_add_another_context_with_partial_submit_data(self, factories):
        group = factories.group.build(add_another=True)
        q1 = factories.question.build(parent=group)
        q2 = factories.question.build(parent=group)
        q3 = factories.question.build(parent=group)
        submission = factories.submission.build(collection=group.form.collection)
        submission.data = {
            str(group.id): [
                {str(q1.id): "v0", str(q2.id): "e0"},
                {str(q2.id): "e1"},
                {str(q1.id): "v2"},
            ]
        }

        context = ExpressionContext.build_expression_context(
            collection=group.form.collection,
            submission_helper=SubmissionHelper(submission=submission),
            mode="evaluation",
        )
        assert context.get(q1.safe_qid_all_answers) == ["v0", None, "v2"]
        assert context.get(q2.safe_qid_all_answers) == ["e0", "e1", None]
        assert context.get(q3.safe_qid_all_answers) == [None, None, None]

        context = context.with_add_another_context(component=q1, add_another_index=1)
        assert context.get(q1.safe_qid) is None
        assert context.get(q2.safe_qid) == "e1"
        assert context.get(q3.safe_qid) is None

    def test_extending_with_existing_context(self, factories):
        component = factories.question.build(add_another=True)
        ex = ExpressionContext(submission_data={"a": [1, 2, 3], "b": 1, "c": 1}, add_another_context={"a": 1})
        with pytest.raises(ValueError) as e:
            ex.with_add_another_context(component, add_another_index=0)
        assert str(e.value) == "add_another_context is already set on this ExpressionContext"

    def test_extending_with_non_add_another_component(self, factories):
        component = factories.question.build(add_another=False)
        ex = ExpressionContext(submission_data={"a": [1, 2, 3], "b": 1, "c": 1})
        with pytest.raises(ValueError) as e:
            ex.with_add_another_context(component, add_another_index=0)
        assert str(e.value) == "add_another_context can only be set for add another components"
