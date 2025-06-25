from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovCheckboxInput, GovRadioInput, GovSubmitInput, GovTextInput
from wtforms import IntegerField, RadioField, SubmitField
from wtforms.fields.simple import BooleanField
from wtforms.validators import DataRequired, Optional

from app.common.data.models import Expression, Question
from app.common.data.types import ManagedExpressionsEnum
from app.common.expressions.managed import Between, GreaterThan, LessThan

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


class _BaseExpressionForm(FlaskForm):
    @abstractmethod
    def get_expression(self, question: Question) -> "ManagedExpression": ...

    @staticmethod
    @abstractmethod
    def from_expression(expression: "Expression") -> "_BaseExpressionForm": ...


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
                self.bottom_of_range.validators = [DataRequired("Enter the minimum value allowed for this question")]
                self.top_of_range.validators = [DataRequired("Enter the maximum value allowed for this question")]

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
        data = {"type": expression.context["key"]}

        match data["type"]:
            case ManagedExpressionsEnum.GREATER_THAN:
                data["greater_than_value"] = expression.context["minimum_value"]
                data["greater_than_inclusive"] = expression.context["inclusive"]
            case ManagedExpressionsEnum.LESS_THAN:
                data["less_than_value"] = expression.context["maximum_value"]
                data["less_than_inclusive"] = expression.context["inclusive"]
            case ManagedExpressionsEnum.BETWEEN:
                data["bottom_of_range"] = expression.context["minimum_value"]
                data["bottom_inclusive"] = expression.context["minimum_inclusive"]
                data["top_of_range"] = expression.context["maximum_value"]
                data["top_inclusive"] = expression.context["maximum_inclusive"]

        return AddIntegerExpressionForm(data=data)
