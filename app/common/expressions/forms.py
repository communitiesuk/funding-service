from typing import TYPE_CHECKING

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput
from markupsafe import Markup
from wtforms import RadioField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.models import Expression, Question
from app.common.data.types import ExpressionType
from app.common.expressions.registry import (
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
)

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


class _ManagedExpressionForm(FlaskForm):
    _managed_expressions: list[type["ManagedExpression"]]
    _referenced_question: Question
    type: RadioField

    def get_managed_expression_radio_conditional_items(self) -> list[dict[str, dict[str, Markup]]]:
        items = []
        for _managed_expression in self._managed_expressions:
            # format the radio items for `govuk-frontend-wtf` macro syntax
            items.append(
                {
                    "conditional": {
                        "html": _managed_expression.concatenate_all_wtf_fields_html(
                            self, referenced_question=self._referenced_question
                        )
                    }
                }
            )
        return items

    def validate(self, extra_validators=None):  # type: ignore[no-untyped-def]
        for _managed_expression in self._managed_expressions:
            if _managed_expression.name == self.type.data:
                _managed_expression.update_validators(self)

        return super().validate(extra_validators=extra_validators)

    def get_expression(self, question: Question) -> "ManagedExpression":
        for _managed_expression in self._managed_expressions:
            if _managed_expression.name == self.type.data:
                return _managed_expression.build_from_form(self, question)

        raise RuntimeError(f"Unknown expression type: {self.type.data}")


def build_managed_expression_form(  # noqa: C901
    type_: ExpressionType, referenced_question: Question, expression: Expression | None = None
) -> type["_ManagedExpressionForm"] | None:
    """
    For a given question, generate a FlaskForm that will allow a user to select one of its managed expressions.

    We take a question instance rather than the data type, as some managed expressions may refer to values on the
    question itself (eg radios, checkboxes).

    Each managed expression declares the data that defines it, and has hooks that can be used to attach, validate, and
    render the specific form fields it needs.

    The form is constructed dynamically from the definition of all registered managed expressions; each one lists
    the question types that can be a condition for, and that it can validate against.
    """
    match type_:
        case ExpressionType.CONDITION:
            type_validation_message = "Select what the answer should be to show this question"
            managed_expressions = get_managed_conditions_by_data_type(referenced_question.data_type)
        case ExpressionType.VALIDATION:
            type_validation_message = "Select the kind of validation to apply"
            managed_expressions = get_managed_validators_by_data_type(referenced_question.data_type)
        case _:
            raise RuntimeError("unknown expression type")

    if not managed_expressions:
        return None

    class ManagedExpressionForm(_ManagedExpressionForm):
        _referenced_question = referenced_question
        _managed_expressions = managed_expressions

        type = RadioField(
            choices=[(managed_expression.name, managed_expression.name) for managed_expression in managed_expressions],
            default=expression.managed_name if expression else None,
            validators=[DataRequired(type_validation_message)],
            widget=GovRadioInput(),
        )

        submit = SubmitField("Add validation", widget=GovSubmitInput())

    for managed_expression in managed_expressions:
        pass_expression = expression and expression.managed_name == managed_expression.name
        for field_name, field in managed_expression.get_form_fields(
            expression=expression if pass_expression else None, referenced_question=referenced_question
        ).items():
            setattr(ManagedExpressionForm, field_name, field)

    return ManagedExpressionForm
