from typing import TYPE_CHECKING, Any, Protocol, cast

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from markupsafe import Markup
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.interfaces.collections import (
    IncompatibleDataTypeException,
    IncompatibleDataTypeInCalculationException,
    _find_all_references_in_expression,
    _validate_reference,
)
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.exceptions import WTFormRenderableException
from app.common.expressions import (
    DisallowedExpression,
    ExpressionContext,
    InvalidEvaluationResult,
    get_restricted_evaluator,
    run_evaluation,
)
from app.common.expressions.registry import (
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
    lookup_managed_expression,
)
from app.metrics import MetricAttributeName, MetricEventName, emit_metric_count

if TYPE_CHECKING:
    from app.common.data.models import Component, Expression, Question
    from app.common.expressions.managed import ManagedExpression


class _ManagedExpressionForm(FlaskForm):
    _managed_expressions: list[type[ManagedExpression]]
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

    def validate(self, extra_validators=None):
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


def build_managed_expression_form(
    type_: ExpressionType,
    referenced_question: Question,
    expression: Expression | None = None,
    show_calculated_validation_option: bool = False,
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
        _show_calculated_validation_option = show_calculated_validation_option

        type = RadioField(
            choices=[],
            default=expression.managed_name if expression else None,
            validators=[DataRequired(type_validation_message)],
            widget=GovRadioInput(),
        )
        submit = SubmitField("Add validation", widget=GovSubmitInput())

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.type.choices = [
                (managed_expression.name, managed_expression.name) for managed_expression in self._managed_expressions
            ]
            if (
                self._show_calculated_validation_option
                and self._referenced_question.data_type == QuestionDataType.NUMBER
            ):
                # This creates a placeholder which is then replaced by the 'or' divider at render time below
                self.type.choices.append((None, None))
                self.type.choices.append(("CUSTOM", "Calculation with two or more numbers"))

        def get_managed_expression_radio_items(self) -> list[dict[str, dict[str, Markup]]]:
            items = super().get_managed_expression_radio_conditional_items()
            if self._show_calculated_validation_option:
                items.append({"divider": "or"})  # ty:ignore[invalid-argument-type]
                items.append({"hint": {"text": "Adding, subtracting, multiplying and dividing"}})  # ty:ignore[invalid-argument-type]
            return items

    for managed_expression in managed_expressions:
        pass_expression = expression and expression.managed_name == managed_expression.name
        for field_name, field in managed_expression.get_form_fields(
            expression=expression if pass_expression else None, referenced_question=referenced_question
        ).items():
            setattr(ManagedExpressionForm, field_name, field)

    return ManagedExpressionForm


class HasFormErrors(Protocol):
    form_errors: list[str]


class ExceptionRenderingFormMixin:
    def handle_exception(self: HasFormErrors, e: WTFormRenderableException, field_name: str | None = None) -> None:
        if e.field_name:
            field_with_error = getattr(self, e.field_name)
        elif field_name:
            field_with_error = getattr(self, field_name)
        else:
            self.form_errors.append(e.form_error_message)
            return
        field_with_error.errors.append(e.form_error_message)


# TODO break this down so it's less complicated
def _validate_custom_syntax(  # noqa:C901
    component: Component,
    expression_context: ExpressionContext,
    statement: str,
    expression_type: ExpressionType,
    field_name: str,
    validate_with_evaluation: bool = True,
) -> None:
    validated_references = []

    try:
        unvalidated_references = _find_all_references_in_expression(statement)
        for ref in unvalidated_references:
            unwrapped_ref = _validate_reference(
                wrapped_reference=ref,
                attached_to_component=component,
                expression_context=expression_context,
                expression_type=expression_type,
                field_name_for_error_message=field_name,
                question_to_test=None,
            )
            validated_references.append(unwrapped_ref)

        if not validate_with_evaluation:
            # No further validation needed for custom error message
            return

        if expression_type == ExpressionType.VALIDATION and component.is_question:
            references_to_self_count = validated_references.count(cast("Question", component).safe_qid)
            if references_to_self_count != 1:
                raise DisallowedExpression(
                    message=(
                        f"Expression contains {references_to_self_count} references to question {component.id}, "
                        "should contain exactly 1"
                    ),
                    form_error_message="The expression must include exactly one reference to this question",
                )

        names = {}
        for ref in validated_references:
            # assume these are numbers as we can't do custom expressions unless using non number data
            # types but we could check this
            names[ref] = 1
        evaluator = get_restricted_evaluator(names=names, required_functions={})

        result = run_evaluation(evaluator, statement)
        if not isinstance(result, bool):
            raise InvalidEvaluationResult(statement, result, bool)

    except WTFormRenderableException as e:
        emit_metric_count(
            MetricEventName.CALCULATION_FIELD_INVALID,
            1,
            custom_attributes={
                MetricAttributeName.CALCULATION_INVALID_FIELD: field_name,
                MetricAttributeName.CALCULATION_INVALID_REASON: e.__class__.__name__,
            },
        )
        if isinstance(e, IncompatibleDataTypeException):
            raise IncompatibleDataTypeInCalculationException(e) from e
        raise


class CustomValidationExpressionForm(ExceptionRenderingFormMixin, FlaskForm):
    def is_submitted_to_add_context(self) -> bool:
        return bool(self.is_submitted() and self.add_context.data and not self.submit.data)

    custom_expression = StringField(
        "Expression",
        widget=GovTextArea(),
        validators=[DataRequired()],
    )
    custom_message = StringField(
        "Message",
        description="Shown to the user if the answer is not valid",
        widget=GovTextArea(),
        validators=[DataRequired()],
    )
    add_context = StringField(
        "Reference data",
        widget=GovSubmitInput(),
    )
    submit = SubmitField("Add validation", widget=GovSubmitInput())

    def __init__(self, *args, question: Question, expression_context: ExpressionContext, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        self.expression_context = expression_context

    def get_expression_form_data(self) -> dict[str, Any]:
        data = {
            "custom_expression": self.custom_expression.data,
            "custom_message": self.custom_message.data,
            "add_context": self.add_context.data,
        }
        return data

    def validate(self, extra_validators=None) -> bool:

        if not super().validate(extra_validators):
            return False

        try:
            _validate_custom_syntax(
                self.question,
                self.expression_context,
                self.custom_expression.data,  # ty:ignore[invalid-argument-type]
                ExpressionType.VALIDATION,
                "custom_expression",
                validate_with_evaluation=True,
            )
            _validate_custom_syntax(
                self.question,
                self.expression_context,
                self.custom_message.data,  # ty:ignore[invalid-argument-type]
                ExpressionType.VALIDATION,
                "custom_message",
                validate_with_evaluation=False,
            )

        except WTFormRenderableException as e:
            self.handle_exception(e, field_name="custom_message")
            return False

        return True


class CalculatedConditionForm(ExceptionRenderingFormMixin, FlaskForm):
    def is_submitted_to_add_context(self) -> bool:
        return bool(self.is_submitted() and self.add_context.data and not self.submit.data)

    expression_name = StringField("Condition name", widget=GovTextInput(), validators=[DataRequired()])

    custom_expression = StringField(
        "Calculation",
        widget=GovTextArea(),
        validators=[DataRequired()],
    )
    add_context = StringField(
        "Reference data",
        widget=GovSubmitInput(),
    )
    submit = SubmitField("Add calculated condition", widget=GovSubmitInput())

    def __init__(self, *args, component: Component, expression_context: ExpressionContext, **kwargs):
        super().__init__(*args, **kwargs)
        self.component = component
        self.expression_context = expression_context

    def get_expression_form_data(self) -> dict[str, Any]:
        data = {
            "expression_name": self.expression_name.data,
            "custom_expression": self.custom_expression.data,
            "add_context": self.add_context.data,
        }
        return data

    def validate(self, extra_validators=None) -> bool:

        if not super().validate(extra_validators):
            return False

        try:
            _validate_custom_syntax(
                self.component,
                self.expression_context,
                self.custom_expression.data,  # ty:ignore[invalid-argument-type]
                ExpressionType.CONDITION,
                "custom_expression",
                validate_with_evaluation=True,
            )
        except WTFormRenderableException as e:
            self.handle_exception(e)
            return False

        return True
