import uuid
from typing import Callable, ClassVar
from typing import Optional as TOptional

import pytest
from immutabledict import immutabledict
from wtforms.fields.core import Field

from app import QuestionDataType
from app.common.data.models import Expression, Question
from app.common.expressions import DisallowedExpression, ExpressionContext, evaluate
from app.common.expressions.forms import _ManagedExpressionForm
from app.common.expressions.managed import GreaterThan, ManagedExpression
from app.common.expressions.registry import register_managed_expression


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


def _custom_test_function():
    return 42


# @register_managed_expression
class CustomManagedExpression(ManagedExpression):
    name = "CustomManagedExpression"
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {}  # type: ignore[assignment]
    _key = "CustomManagedExpression"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} >= custom_test_function()"

    @property
    def description(self) -> str:
        return ""

    @property
    def message(self) -> str:
        return ""

    @property
    def required_functions(self) -> dict[str, Callable]:
        return dict(custom_test_function=_custom_test_function)

    @staticmethod
    def get_form_fields(
        expression: TOptional[Expression] = None, referenced_question: TOptional[Question] = None
    ) -> dict[str, Field]:
        return dict()

    @staticmethod
    def update_validators(form: _ManagedExpressionForm) -> None:
        pass

    @staticmethod
    def build_from_form(form: _ManagedExpressionForm, question: Question) -> "ManagedExpression":
        pass


# @register_managed_expression
class CustomBuiltInManagedExpression(CustomManagedExpression):
    name = "CustomBuiltInManagedExpression"
    _key = "CustomBuiltInManagedExpression"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} >= min(1,2)"

    @property
    def required_functions(self) -> dict[str, Callable]:
        return dict(min=min)


class TestEvaluatingManagedExpressionsWithRequiredFunctions:
    @pytest.fixture(autouse=True)
    def _register_managed_expressions(self):
        """
        This fixture registers our custom managed expression classes above. Using the annotation on the classes directly
        means they exist for all other tests in a test run, which causes failures when we are checking what types of
        managed expressions are available.
        """

        def _deregister_managed_expression(managed_expression_cls: type[ManagedExpression]):
            from app.common.expressions import registry

            registry._registry_by_expression_enum.pop(managed_expression_cls.name, None)
            for data_type in managed_expression_cls.supported_condition_data_types:
                if data_type in registry._condition_registry_by_data_type:
                    registry._condition_registry_by_data_type[data_type] = [
                        cls
                        for cls in registry._condition_registry_by_data_type[data_type]
                        if cls != managed_expression_cls
                    ]
            for data_type in managed_expression_cls.supported_validator_data_types:
                if data_type in registry._validator_registry_by_data_type:
                    registry._validator_registry_by_data_type[data_type] = [
                        cls
                        for cls in registry._validator_registry_by_data_type[data_type]
                        if cls != managed_expression_cls
                    ]

        register_managed_expression(CustomManagedExpression)
        register_managed_expression(CustomBuiltInManagedExpression)
        yield
        # Cleanup the registry
        _deregister_managed_expression(CustomManagedExpression)
        _deregister_managed_expression(CustomBuiltInManagedExpression)

    def test_managed_expression_with_custom_required_function_true(self, factories):
        expr = CustomManagedExpression(question_id=uuid.uuid4(), _key="CustomManagedExpression")  # type:ignore
        assert (
            evaluate(
                Expression(
                    managed_name="CustomManagedExpression",  # type:ignore
                    statement=expr.statement,
                    context={"question_id": expr.question_id, expr.safe_qid: 500},
                )
            )
            is True
        )

    def test_managed_expression_with_custom_required_function_false(self, factories):
        expr = CustomManagedExpression(question_id=uuid.uuid4(), _key="CustomManagedExpression")  # type:ignore
        assert (
            evaluate(
                Expression(
                    managed_name="CustomManagedExpression",  # type:ignore
                    statement=expr.statement,
                    context={"question_id": expr.question_id, expr.safe_qid: 3},
                )
            )
            is False
        )

    def test_managed_expression_with_builtin_required_function(self, factories):
        expr = CustomBuiltInManagedExpression(question_id=uuid.uuid4(), _key="CustomBuiltInManagedExpression")  # type:ignore
        assert (
            evaluate(
                Expression(
                    managed_name="CustomBuiltInManagedExpression",  # type:ignore
                    statement=expr.statement,
                    context={"question_id": expr.question_id, expr.safe_qid: 100},
                )
            )
            is True
        )

    def test_managed_expression_with_required_function_not_present(self, factories):
        expr = CustomManagedExpression(question_id=uuid.uuid4(), _key="CustomManagedExpression")  # type:ignore

        def _temp_test_function():
            return 0

        # Test with a custom function we haven't added to required_functions
        with pytest.raises(DisallowedExpression):
            evaluate(
                Expression(
                    managed_name="CustomManagedExpression",  # type:ignore
                    statement=f"{expr.safe_qid} >= _temp_test_function()",
                    context={"question_id": expr.question_id, expr.safe_qid: 500},
                )
            )

        # Test with a builtin function that isn't on the allowed list
        with pytest.raises(DisallowedExpression):
            evaluate(
                Expression(
                    managed_name="CustomManagedExpression",  # type:ignore
                    statement=f"{expr.safe_qid} >= max(1,2)",
                    context={"question_id": expr.question_id, expr.safe_qid: 500},
                )
            )
