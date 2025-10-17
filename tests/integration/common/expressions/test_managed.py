import datetime
import uuid

import pytest

from app.common.data.interfaces.collections import get_question_by_id
from app.common.data.models import Expression
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
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
from app.deliver_grant_funding.session_models import AddContextToExpressionsModel
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

    def test_prepare_form_data_removes_add_context(self, factories):
        question = factories.question.create(data_type=QuestionDataType.INTEGER)
        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "type": "Greater than",
                "greater_than_value": 100,
                "greater_than_inclusive": True,
                "add_context": "greater_than_expression",  # This should be removed
            },
            component_id=question.id,
        )

        prepared_data = GreaterThan.prepare_form_data(session_data)

        assert "add_context" not in prepared_data
        assert prepared_data == {
            "type": "Greater than",
            "greater_than_value": 100,
            "greater_than_inclusive": True,
        }

    def test_base_prepare_form_data_with_no_add_context_field(self, factories):
        question = factories.question.create(data_type=QuestionDataType.INTEGER)
        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "type": "Greater than",
                "greater_than_value": 100,
                "greater_than_inclusive": True,
            },
            component_id=question.id,
        )

        prepared_data = GreaterThan.prepare_form_data(session_data)

        assert prepared_data == session_data.expression_form_data


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

    @pytest.mark.parametrize(
        "inclusive, answer, expected_result",
        (
            (False, 999, False),
            (False, 1000, False),
            (True, 1000, True),
            (False, 1001, True),
        ),
    )
    def test_evaluate_with_reference(self, inclusive, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.INTEGER)
        expr = GreaterThan(
            question_id=target_question.id,
            minimum_value=None,
            minimum_expression=f"(({referenced_question.safe_qid}))",
            inclusive=inclusive,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            referenced_question.safe_qid: 1000,
            target_question.safe_qid: answer,
            "question_id": expr.question_id,
            "minimum_value": expr.minimum_value,
        }
        assert evaluate(expression) is expected_result

    def test_expression_referenced_question_ids(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.INTEGER)
        expr = GreaterThan(
            question_id=target_question.id,
            minimum_value=None,
            minimum_expression=f"(({referenced_question.safe_qid}))",
        )
        assert expr.expression_referenced_question_ids == [referenced_question.id]


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

    @pytest.mark.parametrize(
        "inclusive, answer, expected_result",
        (
            (False, 999, True),
            (False, 1000, False),
            (True, 1000, True),
            (False, 1001, False),
        ),
    )
    def test_evaluate_with_reference(self, inclusive, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.INTEGER)
        expr = LessThan(
            question_id=target_question.id,
            maximum_value=None,
            maximum_expression=f"(({referenced_question.safe_qid}))",
            inclusive=inclusive,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            referenced_question.safe_qid: 1000,
            target_question.safe_qid: answer,
            "question_id": expr.question_id,
            "maximum_value": expr.maximum_value,
        }
        assert evaluate(expression) is expected_result

    def test_expression_referenced_question_ids(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.INTEGER)
        expr = LessThan(
            question_id=target_question.id,
            maximum_value=None,
            maximum_expression=f"(({referenced_question.safe_qid}))",
        )
        assert expr.expression_referenced_question_ids == [referenced_question.id]


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

    @pytest.mark.parametrize(
        "minimum_inclusive, maximum_inclusive, answer, expected_result",
        (
            (False, False, 0, False),
            (True, False, 0, True),
            (False, False, 1, True),
            (False, False, 999, True),
            (False, False, 1000, False),
            (True, True, 1000, True),
        ),
    )
    def test_evaluate_with_reference(
        self,
        minimum_inclusive,
        maximum_inclusive,
        answer,
        expected_result,
        factories,
    ):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.INTEGER)
        expr = Between(
            question_id=target_question.id,
            minimum_value=0,
            minimum_inclusive=minimum_inclusive,
            maximum_value=None,
            maximum_expression=f"(({referenced_question.safe_qid}))",
            maximum_inclusive=maximum_inclusive,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            referenced_question.safe_qid: 1000,
            target_question.safe_qid: answer,
            "question_id": expr.question_id,
            "minimum_value": expr.minimum_value,
            "maximum_value": expr.maximum_value,
        }
        assert evaluate(expression) is expected_result

    def test_expression_referenced_question_ids(self, factories):
        first_referenced_question = factories.question.create(data_type=QuestionDataType.INTEGER)
        second_referenced_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.INTEGER
        )
        target_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.INTEGER
        )
        expr = Between(
            question_id=target_question.id,
            minimum_value=None,
            minimum_expression=f"(({first_referenced_question.safe_qid}))",
            maximum_value=None,
            maximum_expression=f"(({second_referenced_question.safe_qid}))",
        )
        assert expr.expression_referenced_question_ids == [first_referenced_question.id, second_referenced_question.id]


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
    def test_evaluate(self, inclusive, answer, expected_result, factories):
        user = factories.user.create()
        expr = IsBefore(question_id=uuid.uuid4(), latest_value=self.maximum_value, inclusive=inclusive)
        expression = Expression.from_managed(expr, user)
        expression.context = {expr.safe_qid: answer, "latest_value": expr.latest_value, "question_id": expr.question_id}
        assert evaluate(expression) is expected_result

    @pytest.mark.parametrize(
        "inclusive, answer, expected_result",
        (
            (False, maximum_value - datetime.timedelta(days=2), True),
            (False, maximum_value, False),
            (True, maximum_value, True),
            (False, maximum_value + datetime.timedelta(days=2), False),
        ),
    )
    def test_evaluate_with_reference(self, inclusive, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        expr = IsBefore(
            question_id=target_question.id,
            latest_value=None,
            latest_expression=f"(({referenced_question.safe_qid}))",
            inclusive=inclusive,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            referenced_question.safe_qid: self.maximum_value,
            target_question.safe_qid: answer,
            "question_id": expr.question_id,
            "latest_value": expr.latest_value,
        }
        assert evaluate(expression) is expected_result

    def test_is_before_prepare_form_data_converts_date_string(self, factories):
        question = factories.question.create(data_type=QuestionDataType.DATE)
        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.IS_BEFORE,
            expression_form_data={
                "type": "Is after",
                "latest_value": "2025-01-15",
                "latest_inclusive": False,
                "add_context": "latest_expression",
            },
            component_id=question.id,
        )

        prepared_data = IsBefore.prepare_form_data(session_data)

        assert "add_context" not in prepared_data
        assert prepared_data["latest_value"] == datetime.date(2025, 1, 15)

    def test_expression_referenced_question_ids(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        expr = IsBefore(
            question_id=target_question.id,
            latest_value=None,
            latest_expression=f"(({referenced_question.safe_qid}))",
        )
        assert expr.expression_referenced_question_ids == [referenced_question.id]


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
    def test_evaluate(self, inclusive, answer, expected_result, factories):
        user = factories.user.create()
        expr = IsAfter(question_id=uuid.uuid4(), earliest_value=self.min_value, inclusive=inclusive)
        expression = Expression.from_managed(expr, user)
        expression.context = {
            expr.safe_qid: answer,
            "earliest_value": expr.earliest_value,
            "question_id": expr.question_id,
        }
        assert evaluate(expression) is expected_result

    @pytest.mark.parametrize(
        " inclusive, answer, expected_result",
        (
            (False, min_value - datetime.timedelta(days=2), False),
            (False, min_value, False),
            (True, min_value, True),
            (False, min_value + datetime.timedelta(days=2), True),
        ),
    )
    def test_evaluate_with_reference(self, inclusive, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        expr = IsAfter(
            question_id=target_question.id,
            earliest_value=None,
            earliest_expression=f"(({referenced_question.safe_qid}))",
            inclusive=inclusive,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            referenced_question.safe_qid: self.min_value,
            target_question.safe_qid: answer,
            "earliest_value": expr.earliest_value,
            "question_id": expr.question_id,
        }

        assert evaluate(expression) is expected_result

    def test_is_after_prepare_form_data_converts_date_string(self, factories):
        question = factories.question.create(data_type=QuestionDataType.DATE)
        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.IS_AFTER,
            expression_form_data={
                "type": "Is after",
                "earliest_value": "2025-01-15",
                "earliest_inclusive": False,
                "add_context": "earliest_expression",
            },
            component_id=question.id,
        )

        prepared_data = IsAfter.prepare_form_data(session_data)

        assert "add_context" not in prepared_data
        assert prepared_data["earliest_value"] == datetime.date(2025, 1, 15)

    def test_expression_referenced_question_ids(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        expr = IsAfter(
            question_id=target_question.id,
            earliest_value=None,
            earliest_expression=f"(({referenced_question.safe_qid}))",
        )
        assert expr.expression_referenced_question_ids == [referenced_question.id]


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
    def test_evaluate(self, earliest_inc, latest_inc, answer, expected_result, factories):
        user = factories.user.create()
        expr = BetweenDates(
            question_id=uuid.uuid4(),
            earliest_value=self.min_value,
            latest_value=self.max_value,
            earliest_inclusive=earliest_inc,
            latest_inclusive=latest_inc,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            expr.safe_qid: answer,
            "earliest_value": expr.earliest_value,
            "latest_value": expr.latest_value,
            "earliest_inclusive": expr.earliest_inclusive,
            "latest_inclusive": expr.latest_inclusive,
            "question_id": expr.question_id,
        }
        assert evaluate(expression) is expected_result

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
    def test_evaluate_with_reference(self, earliest_inc, latest_inc, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        expr = BetweenDates(
            question_id=target_question.id,
            earliest_value=self.min_value,
            earliest_expression=None,
            latest_value=None,
            latest_expression=f"(({referenced_question.safe_qid}))",
            earliest_inclusive=earliest_inc,
            latest_inclusive=latest_inc,
        )
        expression = Expression.from_managed(expr, user)
        expression.context = {
            referenced_question.safe_qid: self.max_value,
            target_question.safe_qid: answer,
            "earliest_value": expr.earliest_value,
            "latest_value": expr.latest_value,
            "earliest_inclusive": expr.earliest_inclusive,
            "latest_inclusive": expr.latest_inclusive,
            "question_id": expr.question_id,
        }
        assert evaluate(expression) is expected_result

    def test_between_dates_prepare_form_data_handles_partial_dates(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.BETWEEN_DATES,
            expression_form_data={
                "type": "Between dates",
                "between_bottom_of_range": "2025-01-01",
                "between_top_of_range_expression": f"(({referenced_question.safe_qid}))",
                "between_bottom_inclusive": True,
                "between_top_inclusive": False,
            },
            component_id=question.id,
        )

        prepared_data = BetweenDates.prepare_form_data(session_data)

        assert prepared_data["between_bottom_of_range"] == datetime.date(2025, 1, 1)
        assert "between_top_of_range" not in prepared_data
        assert prepared_data["between_top_of_range_expression"] == f"(({referenced_question.safe_qid}))"

    def test_expression_referenced_question_ids(self, factories):
        first_referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        second_referenced_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.DATE
        )
        target_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.DATE
        )
        expr = BetweenDates(
            question_id=target_question.id,
            earliest_value=None,
            earliest_expression=f"(({first_referenced_question.safe_qid}))",
            latest_value=None,
            latest_expression=f"(({second_referenced_question.safe_qid}))",
        )
        assert expr.expression_referenced_question_ids == [first_referenced_question.id, second_referenced_question.id]
