import abc

# Define any "managed" expressions that can be applied to common conditions or validations
# that are built through the UI. These will be used alongside custom expressions
from typing import TYPE_CHECKING
from uuid import UUID

from flask_wtf import FlaskForm
from pydantic import BaseModel, TypeAdapter

from app.common.data.types import ManagedExpressions, QuestionDataType
from app.common.expressions import mangle_question_id_for_context
from app.common.expressions.forms import AddNumberConditionForm

if TYPE_CHECKING:
    from app.common.data.models import Expression, Question
    # from app.common.data.models import Question


class BaseExpression(BaseModel):
    key: ManagedExpressions
    question_id: UUID

    @property
    @abc.abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def value(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def expression(self) -> str:
        raise NotImplementedError


class GreaterThan(BaseExpression):
    key: ManagedExpressions = ManagedExpressions.GREATER_THAN
    question_id: UUID
    minimum_value: int

    @property
    def description(self) -> str:
        return "Is greater than"

    @property
    def value(self) -> str:
        return str(self.minimum_value)

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from BaseExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return f"The answer must be {self.minimum_value} or greater"

    @property
    def expression(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        qid = mangle_question_id_for_context(self.question_id)
        return f"{qid} > {self.minimum_value}"


supported_managed_question_types = {QuestionDataType.INTEGER: AddNumberConditionForm}


def get_managed_expression_form(question: "Question") -> "FlaskForm":
    try:
        return supported_managed_question_types[question.data_type]
    except KeyError as e:
        raise ValueError(f"Question type {question.data_type} does not support managed expressions") from e


def get_managed_expression(expression: "Expression") -> BaseExpression:
    # todo: fetching this to know what type is starting to feel strange - maybe this should be a top level property
    match expression.context.get("key"):
        case ManagedExpressions.GREATER_THAN:
            return TypeAdapter(GreaterThan).validate_python(expression.context)
        case _:
            raise ValueError(f"Unsupported managed expression type: {expression.type}")


def get_supported_form_questions(question: "Question") -> list["Question"]:
    questions = question.form.questions
    return [q for q in questions if q.data_type in supported_managed_question_types.keys() and q.id != question.id]


def parse_expression_form(question: "Question", form: FlaskForm) -> BaseExpression:
    if isinstance(form, AddNumberConditionForm):
        assert form.value.data
        return GreaterThan(question_id=question.id, minimum_value=form.value.data)
    else:
        raise ValueError("Question type does not support managed expressions.")
