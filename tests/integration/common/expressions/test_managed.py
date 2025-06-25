import uuid

import pytest

from app.common.data.interfaces.collections import add_question_condition, get_question_by_id
from app.common.data.models import Expression
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.expressions import evaluate, mangle_question_id_for_context
from app.common.expressions.forms import AddIntegerExpressionForm
from app.common.expressions.helpers import (
    get_managed_expression_form,
    get_supported_form_questions,
)
from app.common.expressions.managed import Between, GreaterThan, LessThan, get_managed_expression


class TestManagedExpressions:
    def test_get_supported_form_questions_filters_question_types(self, factories):
        form = factories.form.build()
        factories.question.build_batch(3, data_type=QuestionDataType.TEXT_SINGLE_LINE, form=form)
        only_supported_target = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)
        question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        supported_questions = get_supported_form_questions(question)
        assert len(supported_questions) == 1
        assert supported_questions[0].id == only_supported_target.id

    def test_get_supported_form_questions_filters_out_the_current_question(self, factories):
        form = factories.form.build()
        valid_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        assert get_supported_form_questions(valid_question) == []

        second_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        # make sure the original question under test does show up in the correct circumstances
        assert get_supported_form_questions(second_question) == [valid_question]
        assert get_supported_form_questions(valid_question) == [second_question]

    def test_get_managed_expression_form_valid_question_type(self, factories):
        question = factories.question.build(data_type=QuestionDataType.INTEGER)

        form = get_managed_expression_form(question)
        assert form == AddIntegerExpressionForm

    def test_parse_managed_expression_from_context(self, factories):
        expression = factories.expression.build(
            type=ExpressionType.CONDITION, statement="", managed_type=ManagedExpressionsEnum.GREATER_THAN
        )

        expression.context = {"question_id": str(expression.question.id), "minimum_value": 1000}

        managed_expression = get_managed_expression(expression)
        assert isinstance(managed_expression, GreaterThan)
        assert managed_expression.minimum_value == 1000


class TestBaseManagedExpression:
    def test_gets_referenced_question(self, factories):
        user = factories.user.create()
        question = factories.question.create()
        depends_on_question = factories.question.create(form=question.form)

        add_question_condition(question, user, GreaterThan(question_id=depends_on_question.id, minimum_value=1000))
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
        qid = uuid.uuid4()
        expr = GreaterThan(question_id=qid, minimum_value=minimum_value, inclusive=inclusive)
        assert (
            evaluate(Expression(statement=expr.statement, context={mangle_question_id_for_context(qid): answer}))
            is expected_result
        )


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
        qid = uuid.uuid4()
        expr = LessThan(question_id=qid, maximum_value=maximum_value, inclusive=inclusive)
        assert (
            evaluate(Expression(statement=expr.statement, context={mangle_question_id_for_context(qid): answer}))
            is expected_result
        )


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
        qid = uuid.uuid4()
        expr = Between(
            question_id=qid,
            minimum_value=minimum_value,
            minimum_inclusive=minimum_inclusive,
            maximum_value=maximum_value,
            maximum_inclusive=maximum_inclusive,
        )
        assert (
            evaluate(Expression(statement=expr.statement, context={mangle_question_id_for_context(qid): answer}))
            is expected_result
        )
