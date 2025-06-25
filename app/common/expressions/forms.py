from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovCheckboxInput, GovRadioInput, GovSubmitInput, GovTextInput
from wtforms import IntegerField, RadioField, SubmitField, ValidationError
from wtforms.fields.simple import BooleanField
from wtforms.validators import DataRequired, Optional

from app.common.data.models import Expression, Question
from app.common.data.types import ManagedExpressionsEnum, json_flat_scalars
from app.common.expressions.managed import Between, GreaterThan, LessThan

if TYPE_CHECKING:
    from wtforms import Field

    from app.common.expressions.managed import ManagedExpression


class _BaseExpressionForm(FlaskForm):
    @abstractmethod
    def get_expression(self, question: Question) -> "ManagedExpression": ...

    @staticmethod
    @abstractmethod
    def from_expression(expression: "Expression") -> "_BaseExpressionForm": ...


class BottomOfRangeIsLower:
    def __init__(self, message: str | None = None):
        if not message:
            message = "The minimum value must be lower than the maximum value"
        self.message = message

    def __call__(self, form: "AddIntegerExpressionForm", field: "Field") -> None:
        bottom_of_range = form.bottom_of_range and form.bottom_of_range.data
        top_of_range = form.top_of_range and form.top_of_range.data
        if bottom_of_range and top_of_range:
            if bottom_of_range >= top_of_range:
                raise ValidationError(self.message)


class AddIntegerExpressionForm(_BaseExpressionForm):
    type = RadioField(
        choices=[
            (ManagedExpressionsEnum.GREATER_THAN, ManagedExpressionsEnum.GREATER_THAN.value),
            (ManagedExpressionsEnum.LESS_THAN, ManagedExpressionsEnum.LESS_THAN.value),
            (ManagedExpressionsEnum.BETWEEN, ManagedExpressionsEnum.BETWEEN.value),
        ],
        validators=[DataRequired("Select the kind of comparison to apply")],
        widget=GovRadioInput(),
    )

    greater_than_value = IntegerField("Minimum value", widget=GovTextInput(), validators=[Optional()])
    greater_than_inclusive = BooleanField(
        "An answer of exactly the minimum value is allowed", widget=GovCheckboxInput()
    )
    less_than_value = IntegerField("Maximum value", widget=GovTextInput(), validators=[Optional()])
    less_than_inclusive = BooleanField("An answer of exactly the maximum value is allowed", widget=GovCheckboxInput())
    bottom_of_range = IntegerField("Minimum value", widget=GovTextInput(), validators=[Optional()])
    bottom_inclusive = BooleanField("An answer of exactly the minimum value is allowed", widget=GovCheckboxInput())
    top_of_range = IntegerField("Maximum value", widget=GovTextInput(), validators=[Optional()])
    top_inclusive = BooleanField("An answer of exactly the maximum value is allowed", widget=GovCheckboxInput())

    submit = SubmitField(widget=GovSubmitInput())

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        match self.type.data:
            case ManagedExpressionsEnum.GREATER_THAN.value:
                self.greater_than_value.validators = [DataRequired("Enter the minimum value allowed for this question")]
            case ManagedExpressionsEnum.LESS_THAN.value:
                self.less_than_value.validators = [DataRequired("Enter the maximum value allowed for this question")]
            case ManagedExpressionsEnum.BETWEEN.value:
                self.bottom_of_range.validators = [
                    DataRequired("Enter the minimum value allowed for this question"),
                    BottomOfRangeIsLower("The minimum value must be lower than the maximum value"),
                ]
                self.top_of_range.validators = [
                    DataRequired("Enter the maximum value allowed for this question"),
                    BottomOfRangeIsLower("The maximum value must be higher than the minimum value"),
                ]

        # fixme: IDE realises this is a FlaskForm and bool but mypy is calling it "Any" on pre-commit
        return super().validate(extra_validators=extra_validators)  # type: ignore

    def get_expression(self, question: Question) -> "ManagedExpression":
        if not self.validate():
            raise RuntimeError("Form must be validated before building an expression")

        match self.type.data:
            case ManagedExpressionsEnum.GREATER_THAN.value:
                assert self.greater_than_value.data
                return GreaterThan(
                    question_id=question.id,
                    minimum_value=self.greater_than_value.data,
                    inclusive=self.greater_than_inclusive.data,
                )
            case ManagedExpressionsEnum.LESS_THAN.value:
                assert self.less_than_value.data
                return LessThan(
                    question_id=question.id,
                    maximum_value=self.less_than_value.data,
                    inclusive=self.less_than_inclusive.data,
                )
            case ManagedExpressionsEnum.BETWEEN.value:
                assert self.bottom_of_range.data
                assert self.top_of_range.data
                return Between(
                    question_id=question.id,
                    minimum_value=self.bottom_of_range.data,
                    minimum_inclusive=self.bottom_inclusive.data,
                    maximum_value=self.top_of_range.data,
                    maximum_inclusive=self.top_inclusive.data,
                )

        raise RuntimeError(f"Unknown expression type: {self.type.data}")

    @staticmethod
    def from_expression(expression: "Expression") -> "AddIntegerExpressionForm":
        data: json_flat_scalars = {"type": expression.managed_type.value} if expression.managed_type else {}
        managed = expression.managed

        match expression.managed_type:
            case ManagedExpressionsEnum.GREATER_THAN:
                assert isinstance(managed, GreaterThan)
                data["greater_than_value"] = managed.minimum_value
                data["greater_than_inclusive"] = managed.inclusive
            case ManagedExpressionsEnum.LESS_THAN:
                assert isinstance(managed, LessThan)
                data["less_than_value"] = managed.maximum_value
                data["less_than_inclusive"] = managed.inclusive
            case ManagedExpressionsEnum.BETWEEN:
                assert isinstance(managed, Between)
                data["bottom_of_range"] = managed.minimum_value
                data["bottom_inclusive"] = managed.minimum_inclusive
                data["top_of_range"] = managed.maximum_value
                data["top_inclusive"] = managed.maximum_inclusive

        return AddIntegerExpressionForm(data=data)
