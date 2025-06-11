from app.common.data.interfaces.collections import add_question_condition
from app.common.expressions import evaluate, mangle_question_id_for_context
from app.common.expressions.managed import GreaterThan


class TestEvaluatingManagedExpressions:
    def test_greater_than(self, factories):
        user = factories.user.create()
        question = factories.question.create()
        managed_expression = GreaterThan(minimum_value=3000, question_id=question.id)
        add_question_condition(question, user, managed_expression)

        expr = question.expressions[0]

        # todo: find a smooth way of doing this
        question_id_for_context = mangle_question_id_for_context(question.id)
        assert evaluate(expr, {question_id_for_context: 500}) is False
        assert evaluate(expr, {question_id_for_context: 3000}) is False
        assert evaluate(expr, {question_id_for_context: 3001}) is True
