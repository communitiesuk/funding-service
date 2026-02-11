from typing import TYPE_CHECKING, Any

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea
from markupsafe import Markup
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired

from app.common.data.models import Expression, Question
from app.common.data.types import ExpressionType, ManagedExpressionsEnum
from app.common.expressions.registry import (
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
    lookup_managed_expression,
)

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


class _ManagedExpressionForm(FlaskForm):
    _managed_expressions: list[type[ManagedExpression]]
    _referenced_question: Question
    type: RadioField

    def get_managed_expression_radio_conditional_items(self) -> list[dict[str, dict[str, Markup]]]:
        items = []
        for _managed_expression in self._managed_expressions:
            if _managed_expression.name != ManagedExpressionsEnum.CUSTOM.value:
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

    def is_submitted_to_add_context(self) -> bool:
        """Check if user clicked any managed expression Reference Data button"""
        add_context_field = self._fields.get("add_context")
        return bool(
            self.is_submitted()
            and add_context_field is not None
            and hasattr(add_context_field, "data")
            and add_context_field.data
        )

    def is_submitted_to_remove_context(self) -> bool:
        """Check if user clicked any managed expression Remove Data button"""
        remove_context_field = self._fields.get("remove_context")
        return bool(
            self.is_submitted()
            and remove_context_field is not None
            and hasattr(remove_context_field, "data")
            and remove_context_field.data
        )

    def get_expression_form_data(self) -> dict[str, Any]:
        if not self.type.data:
            return {}
        expression = lookup_managed_expression(ManagedExpressionsEnum(self.type.data))
        expression_keys = expression.get_form_fields(self._referenced_question).keys()
        data = {k: v for k, v in self.data.items() if k in expression_keys}
        return data

    def validate(self, extra_validators=None):  # type: ignore[no-untyped-def]
        if self.is_submitted_to_add_context():
            return True

        for _managed_expression in self._managed_expressions:
            if _managed_expression.name == self.type.data:
                _managed_expression.update_validators(self)

        return super().validate(extra_validators=extra_validators)

    def get_expression(self, question: Question) -> ManagedExpression:
        for _managed_expression in self._managed_expressions:
            if _managed_expression.name == self.type.data:
                return _managed_expression.build_from_form(self, question)

        raise RuntimeError(f"Unknown expression type: {self.type.data}")


def build_managed_expression_form(  # noqa: C901
    type_: ExpressionType,
    referenced_question: Question,
    expression: Expression | None = None,
) -> type[_ManagedExpressionForm] | None:
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
            choices=[
                (managed_expression.name, managed_expression.name)
                for managed_expression in managed_expressions
                if managed_expression.name != ManagedExpressionsEnum.CUSTOM.value
            ],
            default=expression.managed_name if expression else None,
            validators=[DataRequired(type_validation_message)],
            widget=GovRadioInput(),
        )
        submit = SubmitField("Add validation", widget=GovSubmitInput())

    for managed_expression in [me for me in managed_expressions if me.name != ManagedExpressionsEnum.CUSTOM.value]:
        pass_expression = expression and expression.managed_name == managed_expression.name
        for field_name, field in managed_expression.get_form_fields(
            expression=expression if pass_expression else None, referenced_question=referenced_question
        ).items():
            setattr(ManagedExpressionForm, field_name, field)

    return ManagedExpressionForm


class CustomExpressionForm(_ManagedExpressionForm):
    custom_expression = StringField(
        "Expression",
        description="The user's answer will be checked against this expression and must be true for the user "
        "to continue, you can include reference data.",
        widget=GovTextArea(),
        validators=[InputRequired()],
    )
    custom_message = StringField(
        "Message",
        description="Shown to the user if the answer is not valid",
        widget=GovTextArea(),
        validators=[InputRequired()],
    )
    add_context_expression = StringField(
        "Reference data",
        widget=GovSubmitInput(),
    )
    add_context_message = StringField(
        "Reference data",
        widget=GovSubmitInput(),
    )
    submit = SubmitField("Add validation", widget=GovSubmitInput())
