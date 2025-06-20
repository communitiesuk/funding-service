from typing import Callable, Type

from app.common.data.models import Question
from app.common.data.types import QuestionDataType
from app.common.expressions.forms import AddIntegerConditionForm, AddIntegerValidationForm, _BaseExpressionForm

supported_managed_conditions_by_question_type = {QuestionDataType.INTEGER: AddIntegerConditionForm}
supported_managed_validation_by_question_type = {QuestionDataType.INTEGER: AddIntegerValidationForm}


def get_managed_condition_form(question: Question) -> Type["_BaseExpressionForm"] | Callable[[], None]:
    try:
        return supported_managed_conditions_by_question_type[question.data_type]
    except KeyError:
        pass

    return lambda: None


def get_managed_validation_form(question: Question) -> Type["_BaseExpressionForm"] | Callable[[], None]:
    try:
        return supported_managed_validation_by_question_type[question.data_type]
    except KeyError:
        pass

    # FIXME: If no managed validation is available for the question, we can give back a callable that returns nothing.
    #        The view should handle this appropriately and tell the user that there is no validation available. We
    #        should handle this in a more user-friendly way in the long-run (ie guide the user away from ever hitting a
    #        page where we would try to show validation for a question where validation is not available.
    return lambda: None


def get_supported_form_questions(question: Question) -> list[Question]:
    questions = question.form.questions
    return [
        q
        for q in questions
        if q.data_type in supported_managed_conditions_by_question_type.keys() and q.id != question.id
    ]
