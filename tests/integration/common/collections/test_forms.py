import uuid

import pytest

from app.common.collections.forms import build_question_form
from app.common.data import interfaces
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import GreaterThan, LessThan


class TestBuildQuestionForm:
    def test_question_attached_by_id(self, factories):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )

        _FormClass = build_question_form(question, expression_context=ExpressionContext())
        form = _FormClass()

        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")

    @pytest.mark.parametrize(
        "value, error_message",
        (
            (-50, "The answer must be greater than or equal to 0"),
            (1_000, "The answer must be less than 100"),
            (50, None),
        ),
    )
    def test_validation_attached_to_field_and_runs(self, factories, value, error_message):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )
        user = factories.user.build()
        interfaces.collections.add_question_validation(
            question, user, GreaterThan(question_id=question.id, minimum_value=0, inclusive=True)
        )
        interfaces.collections.add_question_validation(
            question, user, LessThan(question_id=question.id, maximum_value=100, inclusive=False)
        )

        _FormClass = build_question_form(question, expression_context=ExpressionContext())
        form = _FormClass(data={"q_e4bd98ab41ef4d23b1e59c0404891e7a": value})

        valid = form.validate()
        if error_message:
            assert valid is False
            assert error_message in form.errors["q_e4bd98ab41ef4d23b1e59c0404891e7a"]
        else:
            assert valid is True
