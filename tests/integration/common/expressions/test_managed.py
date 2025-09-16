import datetime
import uuid

import pytest

from app.common.data.interfaces.collections import get_question_by_id
from app.common.data.models import Expression
from app.common.expressions import evaluate
from app.common.expressions.managed import (
    AnyOf,
    Between,
    BetweenDates,
    GreaterThan,
    IsAfter,
    IsBefore,
    IsNo,
    IsYes,
    LessThan,
    Specifically,
)
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


class TestIsYesExpression:
    @pytest.mark.parametrize(
        "answer, expected_result",
        (
            (True, True),
            (False, False),
        ),
    )
    def test_evaluate(self, answer: str, expected_result: bool):
        expr = IsYes(question_id=uuid.uuid4())
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answer})) is expected_result


class TestIsNoExpression:
    @pytest.mark.parametrize(
        "answer, expected_result",
        (
            (True, False),
            (False, True),
        ),
    )
    def test_evaluate(self, answer: str, expected_result: bool):
        expr = IsNo(question_id=uuid.uuid4())
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answer})) is expected_result


class TestSpecificallyExpression:
    @pytest.mark.parametrize(
        "item, answers, expected_result",
        (
            ({"key": "red", "label": "Red"}, {"red", "blue"}, True),
            ({"key": "blue", "label": "Blue"}, {"red", "blue"}, True),
            (
                {"key": "Red", "label": "Red"},
                {"red", "blue"},
                False,
            ),  # check case sensitivity - as with AnyOf above this shouldn't be able to happen though
            ({"key": "green", "label": "Green"}, {"red", "blue"}, False),
        ),
    )
    def test_evaluate(self, item: TRadioItem, answers: set[str], expected_result: bool):
        expr = Specifically(question_id=uuid.uuid4(), item=item)
        assert evaluate(Expression(statement=expr.statement, context={expr.safe_qid: answers})) is expected_result


class TestIsBeforeExpression:
    maximum_value = datetime.datetime.strptime("2025-01-01", "%Y-%m-%d").date()

    @pytest.mark.parametrize(
        " inclusive, answer, expected_result",
        (
            (False, maximum_value - datetime.timedelta(days=2), True),
            (False, maximum_value, False),
            (True, maximum_value, True),
            (False, maximum_value + datetime.timedelta(days=2), False),
        ),
    )
    def test_evaluate(self, inclusive, answer, expected_result):
        expr = IsBefore(question_id=uuid.uuid4(), latest_value=self.maximum_value, inclusive=inclusive)
        assert (
            evaluate(
                Expression(
                    statement=expr.statement,
                    context={expr.safe_qid: answer, "latest_value": expr.latest_value, "question_id": expr.question_id},
                    managed_name=expr.name,
                )
            )
            is expected_result
        )


class TestIsAfterExpression:
    min_value = datetime.datetime.strptime("2020-01-01", "%Y-%m-%d").date()

    @pytest.mark.parametrize(
        " inclusive, answer, expected_result",
        (
            (False, min_value - datetime.timedelta(days=2), False),
            (False, min_value, False),
            (True, min_value, True),
            (False, min_value + datetime.timedelta(days=2), True),
        ),
    )
    def test_evaluate(self, inclusive, answer, expected_result):
        expr = IsAfter(question_id=uuid.uuid4(), earliest_value=self.min_value, inclusive=inclusive)
        assert (
            evaluate(
                Expression(
                    statement=expr.statement,
                    context={
                        expr.safe_qid: answer,
                        "earliest_value": expr.earliest_value,
                        "question_id": expr.question_id,
                    },
                    managed_name=expr.name,
                )
            )
            is expected_result
        )


class TestIsBetweenDatesExpression:
    min_value = datetime.datetime.strptime("2020-01-01", "%Y-%m-%d").date()
    max_value = datetime.datetime.strptime("2025-01-01", "%Y-%m-%d").date()

    @pytest.mark.parametrize(
        "earliest_inc, latest_inc, answer, expected_result",
        (
            (False, False, min_value - datetime.timedelta(days=2), False),
            (False, False, min_value, False),
            (True, False, min_value, True),
            (True, True, min_value, True),
            (False, False, min_value + datetime.timedelta(days=2), True),
            (True, False, min_value + datetime.timedelta(days=2), True),
            (False, False, max_value + datetime.timedelta(days=2), False),
            (False, False, max_value, False),
            (True, True, max_value, True),
            (False, True, max_value, True),
            (False, False, max_value - datetime.timedelta(days=2), True),
            (False, True, max_value - datetime.timedelta(days=2), True),
        ),
    )
    def test_evaluate(self, earliest_inc, latest_inc, answer, expected_result):
        expr = BetweenDates(
            question_id=uuid.uuid4(),
            earliest_value=self.min_value,
            latest_value=self.max_value,
            earliest_inclusive=earliest_inc,
            latest_inclusive=latest_inc,
        )
        assert (
            evaluate(
                Expression(
                    statement=expr.statement,
                    context={
                        expr.safe_qid: answer,
                        "earliest_value": expr.earliest_value,
                        "latest_value": expr.latest_value,
                        "earliest_inclusive": expr.earliest_inclusive,
                        "latest_inclusive": expr.latest_inclusive,
                        "question_id": expr.question_id,
                    },
                    managed_name=expr.name,
                )
            )
            is expected_result
        )
