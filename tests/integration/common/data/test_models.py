import pytest

from app.common.data.types import ExpressionType, SubmissionModeEnum


class TestSubmissionModel:
    def test_test_submission_property_only_includes_test_submissions(self, factories):
        # what a test name
        collection = factories.collection.create()
        test_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.TEST)
        live_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        assert collection.test_submissions == [test_submission]
        assert collection.live_submissions == [live_submission]


class TestQuestionModel:
    def test_question_property_selects_expressions(self, factories):
        question = factories.question.create()
        condition_expression = factories.expression.create(
            question=question, type=ExpressionType.CONDITION, statement=""
        )
        validation_expression = factories.expression.create(
            question=question, type=ExpressionType.VALIDATION, statement=""
        )
        assert question.conditions == [condition_expression]
        assert question.validations == [validation_expression]

    def test_question_gets_a_valid_expression_that_belongs_to_it(self, factories):
        question = factories.question.create()
        expression = factories.expression.create(question=question, type=ExpressionType.CONDITION, statement="")
        assert question.get_expression(expression.id) == expression

    def test_question_does_not_get_a_valid_expression_that_does_not_belong_to_it(self, factories):
        question = factories.question.create()
        expression_on_other_question = factories.expression.create(type=ExpressionType.CONDITION, statement="")

        with pytest.raises(ValueError) as e:
            question.get_expression(expression_on_other_question.id)

        assert (
            str(e.value)
            == f"Could not find an expression with id={expression_on_other_question.id} in question={question.id}"
        )
