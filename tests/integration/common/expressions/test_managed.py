import datetime
import decimal

import pytest

from app.common.data.interfaces.collections import get_question_by_id
from app.common.data.models import Expression
from app.common.data.types import (
    DataSourceType,
    ExpressionType,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
)
from app.common.expressions import ExpressionContext, evaluate
from app.common.expressions.custom import CustomExpression
from app.common.expressions.forms import CustomValidationExpressionForm
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
    UKPostcode,
)
from app.common.expressions.references import EvaluationStatement, ExpressionReference, InterpolationStatement
from app.deliver_grant_funding.session_models import AddContextToExpressionsModel
from app.types import TRadioItem


class TestBaseManagedExpression:
    def test_gets_referenced_question(self, factories):
        user = factories.user.create()
        depends_on_question = factories.question.create()
        question = factories.question.create(
            form=depends_on_question.form,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(
                        subject_reference=ExpressionReference.from_question(depends_on_question),
                        minimum_value=1000,
                    ),
                    ExpressionType.CONDITION,
                    user,
                )
            ],
        )

        from_db = get_question_by_id(question.id)

        assert from_db.conditions[0].managed.referenced_question.id == depends_on_question.id

    def test_prepare_form_data_removes_add_context(self, factories):
        question = factories.question.create(data_type=QuestionDataType.NUMBER)
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
        question = factories.question.create(data_type=QuestionDataType.NUMBER)
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
            # Additional decimal test cases
            (2.5, False, 2.4, False),  # answer < minimum, both decimals
            (2.5, False, 2.5, False),  # answer == minimum, not inclusive
            (2.5, True, 2.5, True),  # answer == minimum, inclusive
            (2.5, False, 2.6, True),  # answer > minimum, both decimals
            (2, False, 2.1, True),  # integer minimum, decimal answer
            (2.1, False, 2, False),  # decimal minimum, integer answer
            (-1.1, False, -1.2, False),  # negative decimals, answer < minimum
            (-1.1, False, -1.0, True),  # negative decimals, answer > minimum
            (0.0, False, 0.1, True),  # minimum zero, answer positive decimal
            (2.0001, False, 2.0, False),  # very close decimals, answer just below minimum
        ),
    )
    def test_evaluate(self, minimum_value, inclusive, answer, expected_result, factories):
        user = factories.user.build()
        expr = GreaterThan(
            subject_reference=ExpressionReference.from_question(factories.question.build()),
            minimum_value=minimum_value,
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.VALIDATION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "minimum_value": expr.minimum_value,
            "inclusive": expr.inclusive,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

    @pytest.mark.parametrize(
        "inclusive, minimum_value, answer, expected_result",
        (
            (False, 1000, 999, False),
            (False, 1000, 1000, False),
            (True, 1000, 1000, True),
            (False, 1000, 1001, True),
            # Additional decimal test cases
            (False, 2.5, 2.4, False),  # answer < minimum, both decimals
            (False, 2.5, 2.5, False),  # answer == minimum, not inclusive
            (True, 2.5, 2.5, True),  # answer == minimum, inclusive
            (False, 2.5, 2.6, True),  # answer > minimum, both decimals
            (False, 2, 2.1, True),  # integer minimum, decimal answer
            (False, 2.1, 2, False),  # decimal minimum, integer answer
            (False, -1.1, -1.2, False),  # negative decimals, answer < minimum
            (False, -1.1, -1.0, True),  # negative decimals, answer > minimum
            (False, 0.0, 0.1, True),  # minimum zero, answer positive decimal
            (False, 2.0001, 2.0, False),  # very close decimals, answer just below minimum
        ),
    )
    def test_evaluate_with_reference(self, inclusive, minimum_value, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.NUMBER)
        expr = GreaterThan(
            subject_reference=ExpressionReference.from_question(target_question),
            minimum_value=None,
            minimum_expression=ExpressionReference.from_question(referenced_question),
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "minimum_value": expr.minimum_value,
        }

        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(referenced_question): minimum_value,
                        ExpressionReference.from_question(target_question): answer,
                    }
                ),
            )
            is expected_result
        )

    def test_expression_referenced_question_ids(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.NUMBER)
        expr = GreaterThan(
            subject_reference=ExpressionReference.from_question(target_question),
            minimum_value=None,
            minimum_expression=ExpressionReference.from_question(referenced_question),
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
            # Additional decimal test cases
            (2.5, False, 2.4, True),  # answer < maximum, both decimals
            (2.5, False, 2.5, False),  # answer == maximum, not inclusive
            (2.5, True, 2.5, True),  # answer == maximum, inclusive
            (2.5, False, 2.6, False),  # answer > maximum, both decimals
            (2, False, 2.1, False),  # integer maximum, decimal answer
            (2.1, False, 2, True),  # decimal maximum, integer answer
            (-1.1, False, -1.2, True),  # negative decimals, answer < maximum
            (-1.1, False, -1.0, False),  # negative decimals, answer > maximum
            (0.0, False, 0.1, False),  # maximum zero, answer positive decimal
            (2.0001, False, 2.0, True),  # very close decimals, answer just below maximum
        ),
    )
    def test_evaluate(self, maximum_value, inclusive, answer, expected_result, factories):
        user = factories.user.build()
        expr = LessThan(
            subject_reference=ExpressionReference.from_question(factories.question.build()),
            maximum_value=maximum_value,
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.VALIDATION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "maximum_value": expr.maximum_value,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

    @pytest.mark.parametrize(
        "inclusive, maximum_value, answer, expected_result",
        (
            (False, 1000, 999, True),
            (False, 1000, 1000, False),
            (True, 1000, 1000, True),
            (False, 1000, 1001, False),
            # Additional decimal test cases
            (False, 2.5, 2.4, True),  # answer < maximum, both decimals
            (False, 2.5, 2.5, False),  # answer == maximum, not inclusive
            (True, 2.5, 2.5, True),  # answer == maximum, inclusive
            (False, 2.5, 2.6, False),  # answer > maximum, both decimals
            (False, 2, 2.1, False),  # integer maximum, decimal answer
            (False, 2.1, 2, True),  # decimal maximum, integer answer
            (False, -1.1, -1.2, True),  # negative decimals, answer < maximum
            (False, -1.1, -1.0, False),  # negative decimals, answer > maximum
            (False, 0.0, 0.1, False),  # maximum zero, answer positive decimal
            (False, 2.0001, 2.0, True),  # very close decimals, answer just below maximum
        ),
    )
    def test_evaluate_with_reference(self, inclusive, maximum_value, answer, expected_result, factories):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.NUMBER)
        expr = LessThan(
            subject_reference=ExpressionReference.from_question(target_question),
            maximum_value=None,
            maximum_expression=ExpressionReference.from_question(referenced_question),
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "maximum_value": expr.maximum_value,
        }
        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(referenced_question): maximum_value,
                        ExpressionReference.from_question(target_question): answer,
                    }
                ),
            )
            is expected_result
        )

    def test_expression_referenced_question_ids(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.NUMBER)
        expr = LessThan(
            subject_reference=ExpressionReference.from_question(target_question),
            maximum_value=None,
            maximum_expression=ExpressionReference.from_question(referenced_question),
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
            # Additional decimal test cases
            (2.5, False, 5.5, False, 2.4, False),  # below min, all decimals
            (2.5, False, 5.5, False, 2.5, False),  # at min, not inclusive
            (2.5, True, 5.5, False, 2.5, True),  # at min, inclusive
            (2.5, False, 5.5, False, 5.5, False),  # at max, not inclusive
            (2.5, False, 5.5, True, 5.5, True),  # at max, inclusive
            (2.5, False, 5.5, False, 3.0, True),  # between min and max, decimal
            (2, False, 5.5, False, 3, True),  # int min, int answer, decimal max
            (2.5, False, 5, False, 3, True),  # decimal min, int max, int answer
            (2.5, False, 5.5, False, 6.0, False),  # above max, decimal
            (-2.5, True, 2.5, True, 0.0, True),  # negative min, positive max, zero answer
            (-2.5, True, 2.5, True, -2.5, True),  # at min, inclusive, negative
            (-2.5, True, 2.5, True, 2.5, True),  # at max, inclusive, positive
            (-2.5, False, 2.5, False, -2.5, False),  # at min, not inclusive, negative
            (-2.5, False, 2.5, False, 2.5, False),  # at max, not inclusive, positive
            (2.0001, False, 2.0002, False, 2.00015, True),  # very close decimals, answer between
            (2.0001, False, 2.0002, False, 2.00005, False),  # just below min
            (2.0001, False, 2.0002, False, 2.00025, False),  # just above max
        ),
    )
    def test_evaluate(
        self, minimum_value, minimum_inclusive, maximum_value, maximum_inclusive, answer, expected_result, factories
    ):
        expr = Between(
            subject_reference=ExpressionReference.from_question(factories.question.build()),
            minimum_value=minimum_value,
            minimum_inclusive=minimum_inclusive,
            maximum_value=maximum_value,
            maximum_inclusive=maximum_inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.VALIDATION, factories.user.build())
        expression.context = {
            "subject_reference": expr.subject_reference,
            "maximum_value": expr.maximum_value,
            "minimum_value": expr.maximum_value,
            "minimum_inclusive": expr.minimum_inclusive,
            "maximum_inclusive": expr.maximum_inclusive,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

    @pytest.mark.parametrize(
        "minimum_value,minimum_inclusive,maximum_value, maximum_inclusive, answer, expected_result",
        (
            (0, False, 1000, False, 0, False),
            (0, True, 1000, False, 0, True),
            (0, False, 1000, False, 1, True),
            (0, False, 1000, False, 999, True),
            (0, False, 1000, False, 1000, False),
            (0, True, 1000, True, 1000, True),
            # Additional decimal test cases
            (2.5, False, 5.5, False, 2.4, False),  # below min, all decimals
            (2.5, False, 5.5, False, 2.5, False),  # at min, not inclusive
            (2.5, True, 5.5, False, 2.5, True),  # at min, inclusive
            (2.5, False, 5.5, False, 5.5, False),  # at max, not inclusive
            (2.5, False, 5.5, True, 5.5, True),  # at max, inclusive
            (2.5, False, 5.5, False, 3.0, True),  # between min and max, decimal
            (2, False, 5.5, False, 3, True),  # int min, int answer, decimal max
            (2.5, False, 5, False, 3, True),  # decimal min, int max, int answer
            (2.5, False, 5.5, False, 6.0, False),  # above max, decimal
            (-2.5, True, 2.5, True, 0.0, True),  # negative min, positive max, zero answer
            (-2.5, True, 2.5, True, -2.5, True),  # at min, inclusive, negative
            (-2.5, True, 2.5, True, 2.5, True),  # at max, inclusive, positive
            (-2.5, False, 2.5, False, -2.5, False),  # at min, not inclusive, negative
            (-2.5, False, 2.5, False, 2.5, False),  # at max, not inclusive, positive
            (2.0001, False, 2.0002, False, 2.00015, True),  # very close decimals, answer between
            (2.0001, False, 2.0002, False, 2.00005, False),  # just below min
            (2.0001, False, 2.0002, False, 2.00025, False),  # just above max
        ),
    )
    def test_evaluate_with_reference(
        self,
        minimum_value,
        minimum_inclusive,
        maximum_value,
        maximum_inclusive,
        answer,
        expected_result,
        factories,
    ):
        user = factories.user.create()
        referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.NUMBER)
        expr = Between(
            subject_reference=ExpressionReference.from_question(target_question),
            minimum_value=minimum_value,
            minimum_inclusive=minimum_inclusive,
            maximum_value=None,
            maximum_expression=ExpressionReference.from_question(referenced_question),
            maximum_inclusive=maximum_inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "minimum_value": expr.minimum_value,
            "maximum_value": expr.maximum_value,
        }
        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(referenced_question): maximum_value,
                        ExpressionReference.from_question(target_question): answer,
                    }
                ),
            )
            is expected_result
        )

    def test_expression_referenced_question_ids(self, factories):
        first_referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        second_referenced_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.NUMBER
        )
        target_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.NUMBER
        )
        expr = Between(
            subject_reference=ExpressionReference.from_question(target_question),
            minimum_value=None,
            minimum_expression=ExpressionReference.from_question(first_referenced_question),
            maximum_value=None,
            maximum_expression=ExpressionReference.from_question(second_referenced_question),
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
    def test_evaluate(self, items: list[TRadioItem], answer: str, expected_result: bool, factories):
        expr = AnyOf(subject_reference=ExpressionReference.from_question(factories.question.build()), items=items)
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, factories.user.build())
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

    def test_needs_a_question_subject_reference(self, factories):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        data_source_ref = ExpressionReference.from_data_source_column(data_source, "c_allocation")
        items: list[TRadioItem] = [{"key": "red", "label": "Red"}]

        expr = AnyOf(subject_reference=data_source_ref, items=items)

        with pytest.raises(
            ValueError, match="AnyOf managed expressions are only implemented for questions with data sources"
        ):
            expr.get_form_fields(data_source_ref)


class TestIsYesExpression:
    @pytest.mark.parametrize(
        "answer, expected_result",
        (
            (True, True),
            (False, False),
        ),
    )
    def test_evaluate(self, answer: str, expected_result: bool, factories):
        expr = IsYes(subject_reference=ExpressionReference.from_question(factories.question.build()))
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, factories.user.build())
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result


class TestIsNoExpression:
    @pytest.mark.parametrize(
        "answer, expected_result",
        (
            (True, False),
            (False, True),
        ),
    )
    def test_evaluate(self, answer: str, expected_result: bool, factories):
        expr = IsNo(subject_reference=ExpressionReference.from_question(factories.question.build()))
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, factories.user.build())
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result


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
    def test_evaluate(self, item: TRadioItem, answers: set[str], expected_result: bool, factories):
        expr = Specifically(subject_reference=ExpressionReference.from_question(factories.question.build()), item=item)
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, factories.user.build())
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answers})) is expected_result

    def test_needs_a_question_subject_reference(self, factories):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        data_source_ref = ExpressionReference.from_data_source_column(data_source, "c_allocation")
        item: TRadioItem = {"key": "red", "label": "Red"}

        expr = Specifically(subject_reference=data_source_ref, item=item)

        with pytest.raises(
            ValueError, match="Specifically managed expressions are only implemented for questions with data sources"
        ):
            expr.get_form_fields(data_source_ref)


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
        expr = IsBefore(
            subject_reference=ExpressionReference.from_question(factories.question.build()),
            latest_value=self.maximum_value,
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "latest_value": expr.latest_value,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

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
            subject_reference=ExpressionReference.from_question(target_question),
            latest_value=None,
            latest_expression=ExpressionReference.from_question(referenced_question),
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "latest_value": expr.latest_value,
        }
        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(referenced_question): self.maximum_value,
                        ExpressionReference.from_question(target_question): answer,
                    }
                ),
            )
            is expected_result
        )

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
            subject_reference=ExpressionReference.from_question(target_question),
            latest_value=None,
            latest_expression=ExpressionReference.from_question(referenced_question),
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
        expr = IsAfter(
            subject_reference=ExpressionReference.from_question(factories.question.build()),
            earliest_value=self.min_value,
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "earliest_value": expr.earliest_value,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

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
            subject_reference=ExpressionReference.from_question(target_question),
            earliest_value=None,
            earliest_expression=ExpressionReference.from_question(referenced_question),
            inclusive=inclusive,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "earliest_value": expr.earliest_value,
        }

        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(referenced_question): self.min_value,
                        ExpressionReference.from_question(target_question): answer,
                    }
                ),
            )
            is expected_result
        )

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
            subject_reference=ExpressionReference.from_question(target_question),
            earliest_value=None,
            earliest_expression=ExpressionReference.from_question(referenced_question),
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
            subject_reference=ExpressionReference.from_question(factories.question.build()),
            earliest_value=self.min_value,
            latest_value=self.max_value,
            earliest_inclusive=earliest_inc,
            latest_inclusive=latest_inc,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "earliest_value": expr.earliest_value,
            "latest_value": expr.latest_value,
            "earliest_inclusive": expr.earliest_inclusive,
            "latest_inclusive": expr.latest_inclusive,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result

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
            subject_reference=ExpressionReference.from_question(target_question),
            earliest_value=self.min_value,
            earliest_expression=None,
            latest_value=None,
            latest_expression=ExpressionReference.from_question(referenced_question),
            earliest_inclusive=earliest_inc,
            latest_inclusive=latest_inc,
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "earliest_value": expr.earliest_value,
            "latest_value": expr.latest_value,
            "earliest_inclusive": expr.earliest_inclusive,
            "latest_inclusive": expr.latest_inclusive,
        }
        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(referenced_question): self.max_value,
                        ExpressionReference.from_question(target_question): answer,
                    }
                ),
            )
            is expected_result
        )

    def test_between_dates_prepare_form_data_handles_partial_dates(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.BETWEEN_DATES,
            expression_form_data={
                "type": "Between dates",
                "between_bottom_of_range": "2025-01-01",
                "between_top_of_range_expression": ExpressionReference.from_question(referenced_question),
                "between_bottom_inclusive": True,
                "between_top_inclusive": False,
            },
            component_id=question.id,
        )

        prepared_data = BetweenDates.prepare_form_data(session_data)

        assert prepared_data["between_bottom_of_range"] == datetime.date(2025, 1, 1)
        assert "between_top_of_range" not in prepared_data
        assert prepared_data["between_top_of_range_expression"] == ExpressionReference.from_question(
            referenced_question
        )

    def test_expression_referenced_question_ids(self, factories):
        first_referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        second_referenced_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.DATE
        )
        target_question = factories.question.create(
            form=first_referenced_question.form, data_type=QuestionDataType.DATE
        )
        expr = BetweenDates(
            subject_reference=ExpressionReference.from_question(target_question),
            earliest_value=None,
            earliest_expression=ExpressionReference.from_question(first_referenced_question),
            latest_value=None,
            latest_expression=ExpressionReference.from_question(second_referenced_question),
        )
        assert expr.expression_referenced_question_ids == [first_referenced_question.id, second_referenced_question.id]


class TestUKPostcodeExpression:
    @pytest.mark.parametrize(
        "answer, expected_result",
        (
            ("SW1A 1AA", True),
            ("sw1a 1aa", True),
            ("M1 1AE", True),
            ("m1 1ae", True),
            ("CR2 6XH", True),
            ("DN55 1PT", True),
            ("W1A 0AX", True),
            ("W10A 0AX", False),
            ("AA10A 0AX", False),
            ("EC1A 1BB", True),
            ("SW1A1AA", True),
            ("  SW1A 1AA  ", True),
            ("  SW1A1AA  ", True),
            ("invalid", False),
            ("12345", False),
            ("A1 1A", False),
            ("SW1A 1AAA", False),
            ("", False),
            ("   ", False),
        ),
    )
    def test_evaluate(self, answer, expected_result, factories):
        user = factories.user.create()
        expr = UKPostcode(subject_reference=ExpressionReference.from_question(factories.question.build()))
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.CONDITION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
        }
        assert evaluate(expression, ExpressionContext({expr.subject_reference.unwrapped: answer})) is expected_result


class TestCustomExpression:
    def test_create_custom_expression(self, factories, db_session):
        user = factories.user.create()
        question = factories.question.create()
        expr = CustomExpression(
            custom_expression=EvaluationStatement("(({question_id})) > 5"),
            custom_message=InterpolationStatement("Failed validation"),
            expression_name="my short name",
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.VALIDATION, user)
        question.expressions.append(expression)
        db_session.commit()

        from_db = db_session.query(Expression).filter_by(id=expression.id).one()
        assert from_db.statement == expr.custom_expression
        assert from_db.type_ == ExpressionType.VALIDATION
        assert from_db.created_by_id == user.id
        assert from_db.is_custom is True
        assert from_db.is_managed is False
        assert from_db.managed_name is None
        with pytest.raises(ValueError):
            _ = from_db.managed
        assert from_db.custom is not None
        assert from_db.custom.custom_expression == expr.custom_expression
        assert from_db.custom.custom_message == expr.custom_message
        assert from_db.context == {
            "subject_reference": None,
            "custom_expression": "(({question_id})) > 5",
            "custom_message": "Failed validation",
            "expression_name": "my short name",
        }

    @pytest.mark.parametrize(
        " expression, expected_result",
        [
            ("(({q1})) + (({q2})) <= (({q3}))", True),
            ("(({q1})) + (({q2})) < (({q3}))", False),
            ("(({q1})) * (({q2})) > (({q3}))", True),
            ("(({q1})) * 8 >= (({q3}))", True),
            ("(({q4})) * 1.1 >= (({q3}))", True),
        ],
    )
    def test_evaluate(self, expression, expected_result, factories):
        user = factories.user.create()
        form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q4 = factories.question.create(
            form=form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL),
        )
        expr = CustomExpression(
            custom_expression=expression.format(q1=q1.safe_qid, q2=q2.safe_qid, q3=q3.safe_qid, q4=q4.safe_qid),
            custom_message=InterpolationStatement("a message"),
        )
        expression = Expression.from_evaluatable_expression(expr, ExpressionType.VALIDATION, user)
        expression.context = {
            "subject_reference": expr.subject_reference,
            "custom_expression": expr.custom_expression,
            "custom_message": expr.custom_message,
        }

        assert (
            evaluate(
                expression,
                ExpressionContext(
                    {
                        ExpressionReference.from_question(q1): 10,
                        ExpressionReference.from_question(q2): 20,
                        ExpressionReference.from_question(q3): 30,
                        ExpressionReference.from_question(q4): decimal.Decimal("40.4"),
                    }
                ),
            )
            is expected_result
        )

    def test_build_from_form(self, factories):
        question = factories.question.build()
        form = CustomValidationExpressionForm(
            component=question, interpolation_context=ExpressionContext(), evaluation_context=ExpressionContext()
        )
        form.custom_expression.data = "some expression"
        form.custom_message.data = "a message"
        result = CustomExpression.build_from_form(
            form=form,
        )
        assert isinstance(result, CustomExpression)
        assert result.subject_reference is None
        assert result.custom_expression == "some expression"
        assert result.custom_message == "a message"
