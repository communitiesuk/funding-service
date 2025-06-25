import uuid
from typing import Callable, Type

from wtforms import Field
from wtforms import Form as WTForm
from wtforms.validators import ValidationError

from app.common.data.models import Question, Submission
from app.common.data.types import QuestionDataType, json_flat_scalars
from app.common.expressions import evaluate, mangle_question_id_for_context
from app.common.expressions.forms import AddIntegerConditionForm, AddIntegerValidationForm, _BaseExpressionForm

supported_managed_conditions_by_question_type = {QuestionDataType.INTEGER: AddIntegerConditionForm}
supported_managed_validation_by_question_type = {QuestionDataType.INTEGER: AddIntegerValidationForm}


def get_managed_condition_form(question: Question) -> Type["_BaseExpressionForm"] | Callable[[], None]:
    try:
        return supported_managed_conditions_by_question_type[question.data_type]
    except KeyError:
        pass

    return lambda: None


def get_managed_validation_form(question: Question) -> Type["_BaseExpressionForm"] | None:
    try:
        return supported_managed_validation_by_question_type[question.data_type]
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
        if q.data_type in supported_managed_conditions_by_question_type.keys() and q.id != question.id
    ]


def get_validation_supported_for_question(question: Question) -> bool:
    return question.data_type in supported_managed_validation_by_question_type


def build_submission_context(submission: Submission) -> json_flat_scalars:
    return {mangle_question_id_for_context(uuid.UUID(k)): v for k, v in submission.data.items()}


def build_validators(question: "Question", submission: "Submission") -> list[Callable[[WTForm, Field], None]]:
    all_answers_from_submission = build_submission_context(submission)

    validators = []
    for validation in question.validations:
        # note: we use a validator factory so that `validation`, the loop variable, is bound as part of the function
        #       definition. Using it within the function definition otherwise would mean that all validator functions
        #       defined here up pointing at the last validation entry from the question.validations loop, rather than
        #       each one pointing to the loop index that defined the function.
        def validator_factory(_validation=validation):
            def validator(form: WTForm, field: Field) -> None:
                # note: with the `evaluate()` interface as it stands now, we need to take the context from the
                #       submission and inject the answer to the current question to create the 'latest' context that
                #       is relevant for validating against.
                # note: when we support multiple questions per page, we'll need to override the answers to all questions
                #       on the page.
                # note: really don't like the idea of having to unpack the full submission context into a new
                #       copy for every validator for every question in the form, especially as the internals of
                #       `evaluate` currently do another copy of this - lots of copies, mild fear of slow+memory waste.
                context = {**all_answers_from_submission, mangle_question_id_for_context(question.id): field.data}
                if not evaluate(_validation, context):
                    # todo: support non-managed validation
                    raise ValidationError(_validation.managed.message)

            return validator

        validators.append(validator_factory())

    return validators
