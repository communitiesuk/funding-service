from typing import Type

from app.common.data.models import Question
from app.common.data.types import QuestionDataType
from app.common.expressions.forms import AddIntegerExpressionForm, _BaseExpressionForm

supported_managed_expression_by_question_type = {QuestionDataType.INTEGER: AddIntegerExpressionForm}


def get_managed_expression_form(question: Question) -> Type["_BaseExpressionForm"] | None:
    try:
        return supported_managed_expression_by_question_type[question.data_type]
    except KeyError:
        pass

    # FIXME: If no managed validation is available for the question, we can give back a callable that returns nothing.
    #        The view should handle this appropriately and tell the user that there is no validation available. We
    #        should handle this in a more user-friendly way in the long-run (ie guide the user away from ever hitting a
    #        page where we would try to show validation for a question where validation is not available.
    return None


def get_supported_form_questions(question: Question) -> list[Question]:
    questions = question.form.questions
    return [
        q
        for q in questions
        if q.data_type in supported_managed_expression_by_question_type.keys() and q.id != question.id
    ]


def get_validation_supported_for_question(question: Question) -> bool:
    return question.data_type in supported_managed_expression_by_question_type
