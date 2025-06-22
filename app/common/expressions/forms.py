import abc
from abc import abstractmethod
from typing import TYPE_CHECKING, Type

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput
from markupsafe import Markup
from wtforms import RadioField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.models import Expression, Question
from app.common.data.types import ExpressionType, QuestionDataType
from app.common.expressions.registry import (
    get_managed_expressions_for_question_type,
)

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


class _ManagedExpressionForm(FlaskForm):
    @property
    @abstractmethod
    def _question_type(self) -> QuestionDataType:
        """The question data type that this form lists conditions/validation for."""
        ...

    @property
    @abstractmethod
    def type(self) -> RadioField:
        """A RadioField that lists the available managed expressions for the question type."""
        ...

    @abc.abstractmethod
    def get_conditional_field_htmls(self) -> list[dict[str, dict[str, Markup]]]: ...

    @abstractmethod
    def get_expression(self, question: Question) -> "ManagedExpression": ...

    @staticmethod
    @abstractmethod
    def from_expression(expression: "Expression") -> "_ManagedExpressionForm": ...


def build_managed_expression_form(  # noqa: C901
    type_: ExpressionType, question_type: QuestionDataType
) -> Type["_ManagedExpressionForm"] | None:
    """
    For a given question type, generate a FlaskForm that will allow a user to select one of its managed expressions.

    Each managed expression declares the data that defines it, and has hooks that can be used to attach, validate, and
    render the specific form fields it needs.

    The form is constructed dynamically from the definition of all registered managed expressions; each one lists
    the question types that can be a condition for, and that it can validate against.
    """
    managed_expressions = get_managed_expressions_for_question_type(question_type)
    if not managed_expressions:
        return None

    match type_:
        case ExpressionType.CONDITION:
            type_validation_message = "Select what the answer should be to show this question"
        case ExpressionType.VALIDATION:
            type_validation_message = "Select the kind of validation to apply"
        case _:
            raise RuntimeError("unknown expression type")

    class ManagedExpressionForm(_ManagedExpressionForm):
        type = RadioField(
            choices=[(managed_expression.name, managed_expression.name) for managed_expression in managed_expressions],
            validators=[DataRequired(type_validation_message)],
            widget=GovRadioInput(),
        )

        submit = SubmitField("Add validation", widget=GovSubmitInput())

        # FIXME: feels like a crime rendering the HTML this way
        def get_conditional_field_htmls(self) -> list[dict[str, dict[str, Markup]]]:
            html = []
            for _managed_expression in managed_expressions:
                html.append({"conditional": {"html": _managed_expression.render_conditional_fields(self)}})
            return html

        def validate(self, extra_validators=None):  # type: ignore[no-untyped-def]
            for _managed_expression in managed_expressions:
                if _managed_expression.name == self.type.data:
                    _managed_expression.update_validators(self)

            return super().validate(extra_validators=extra_validators)

        def get_expression(self, question: Question) -> "ManagedExpression":
            for _managed_expression in managed_expressions:
                if _managed_expression.name == self.type.data:
                    return _managed_expression.build_from_form(self, question)

            raise RuntimeError(f"Unknown expression type: {self.type.data}")

        @classmethod
        def from_expression(cls, expression: "Expression") -> "_ManagedExpressionForm":
            data = {"type": expression.managed_name}

            for _managed_expression in managed_expressions:
                if _managed_expression.name == expression.managed_name:
                    data.update(_managed_expression.form_data_from_expression(expression))

            return cls(data=data)

    for managed_expression in managed_expressions:
        for field_name, field in managed_expression.get_form_fields().items():
            setattr(ManagedExpressionForm, field_name, field)

    return ManagedExpressionForm
