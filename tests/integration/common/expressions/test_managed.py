import uuid

import pytest

from app.common.data.interfaces.collections import get_question_by_id
from app.common.data.models import Expression
from app.common.expressions import evaluate
from app.common.expressions.managed import AnyOf, Between, GreaterThan, LessThan
from app.types import TRadioItem


class TestBaseManagedExpression:
    def test_gets_referenced_question(self, factories):
        user = factories.user.create()
        depends_on_question = factories.question.create()
        question = factories.question.create(
            form=depends_on_question.form,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=depends_on_question.id, minimum_value=1000), user)
            ],
        )

        from_db = get_question_by_id(question.id)

        assert from_db.conditions[0].managed.referenced_question.id == depends_on_question.id


class TestGreaterThanExpression:
    @pytest.mark.parametrize(
        "minimum_value, inclusive, answer, expected_result",
        (
            (1000, False, 999, False),
            (1000, False, 1000, False),
            (1000, True, 1000, True),
            (1000, False, 1001, True),
        ),
    )
    def test_evaluate(self, minimum_value, inclusive, answer, expected_result):
        expr = GreaterThan(question_id=uuid.uuid4(), minimum_value=minimum_value, inclusive=inclusive)
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answer})) is expected_result


class TestLessThanExpression:
    @pytest.mark.parametrize(
        "maximum_value, inclusive, answer, expected_result",
        (
            (1000, False, 999, True),
            (1000, False, 1000, False),
            (1000, True, 1000, True),
            (1000, False, 1001, False),
        ),
    )
    def test_evaluate(self, maximum_value, inclusive, answer, expected_result):
        expr = LessThan(question_id=uuid.uuid4(), maximum_value=maximum_value, inclusive=inclusive)
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answer})) is expected_result


class TestBetweenExpression:
    @pytest.mark.parametrize(
        "minimum_value, minimum_inclusive, maximum_value, maximum_inclusive, answer, expected_result",
        (
            (0, False, 1000, False, 0, False),
            (0, True, 1000, False, 0, True),
            (0, False, 1000, False, 1, True),
            (0, False, 1000, False, 999, True),
            (0, False, 1000, False, 1000, False),
            (0, True, 1000, True, 1000, True),
        ),
    )
    def test_evaluate(
        self, minimum_value, minimum_inclusive, maximum_value, maximum_inclusive, answer, expected_result
    ):
        expr = Between(
            question_id=uuid.uuid4(),
            minimum_value=minimum_value,
            minimum_inclusive=minimum_inclusive,
            maximum_value=maximum_value,
            maximum_inclusive=maximum_inclusive,
        )
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answer})) is expected_result


class TestAnyOfExpression:
    @pytest.mark.parametrize(
        "items, answer, expected_result",
        (
            ([{"key": "red", "label": "Red"}, {"key": "blue", "label": "Blue"}], "red", True),
            ([{"key": "red", "label": "Red"}, {"key": "blue", "label": "Blue"}], "blue", True),
            (
                [{"key": "red", "label": "Red"}, {"key": "blue", "label": "Blue"}],
                "Blue",
                False,
            ),  # case sensitive - this shouldn't be able to happen, though
            ([{"key": "red", "label": "Red"}, {"key": "blue", "label": "Blue"}], "green", False),
        ),
    )
    def test_evaluate(self, items: list[TRadioItem], answer: str, expected_result: bool):
        expr = AnyOf(question_id=uuid.uuid4(), items=items)
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answer})) is expected_result
