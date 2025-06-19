from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovCheckboxInput, GovRadioInput, GovSubmitInput, GovTextInput
from wtforms import IntegerField, RadioField, SubmitField
from wtforms.fields.simple import BooleanField
from wtforms.validators import DataRequired, Optional

from app.common.data.models import Question
from app.common.data.types import ManagedExpressions
from app.common.expressions.managed import Between, GreaterThan, LessThan

if TYPE_CHECKING:
    from app.common.expressions.managed import BaseExpression


class _BaseExpressionForm(FlaskForm):
    @abstractmethod
    def get_expression(self, question: Question) -> "BaseExpression": ...


class AddNumberConditionForm(FlaskForm):
    type = RadioField(
        "Only show the question if the answer is",
        choices=[(ManagedExpressions.GREATER_THAN, ManagedExpressions.GREATER_THAN.value)],
        validators=[DataRequired("Select what the answer should be to show this question")],
        widget=GovRadioInput(),
    )
    value = IntegerField("Value", widget=GovTextInput(), validators=[Optional()])

    submit = SubmitField("Add condition", widget=GovSubmitInput())

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        if self.type.data:
            self.value.validators = [DataRequired("Enter a value")]

        # fixme: IDE realises this is a FlaskForm and bool but mypy is calling it "Any" on pre-commit
        return super().validate(extra_validators=extra_validators)  # type: ignore


class AddNumberValidationForm(_BaseExpressionForm):
    type = RadioField(
        choices=[
            (ManagedExpressions.GREATER_THAN, ManagedExpressions.GREATER_THAN.value),
            (ManagedExpressions.LESS_THAN, ManagedExpressions.LESS_THAN.value),
            (ManagedExpressions.BETWEEN, ManagedExpressions.BETWEEN.value),
        ],
        validators=[DataRequired("Select the kind of validation to apply")],
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

    submit = SubmitField("Add validation", widget=GovSubmitInput())

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        match self.type.data:
            case ManagedExpressions.GREATER_THAN.value:
                self.greater_than_value.validators = [DataRequired("Enter the minimum value allowed for this question")]
            case ManagedExpressions.LESS_THAN.value:
                self.less_than_value.validators = [DataRequired("Enter the maximum value allowed for this question")]
            case ManagedExpressions.BETWEEN.value:
                self.bottom_of_range.validators = [DataRequired("Enter the minimum value allowed for this question")]
                self.top_of_range.validators = [DataRequired("Enter the maximum value allowed for this question")]

        # fixme: IDE realises this is a FlaskForm and bool but mypy is calling it "Any" on pre-commit
        return super().validate(extra_validators=extra_validators)  # type: ignore

    def get_expression(self, question: Question) -> "BaseExpression":
        if not self.validate():
            raise RuntimeError("Form must be validated before building an expression")

        match self.type.data:
            case ManagedExpressions.GREATER_THAN.value:
                assert self.greater_than_value.data
                return GreaterThan(
                    question_id=question.id,
                    minimum_value=self.greater_than_value.data,
                    inclusive=self.greater_than_inclusive.data,
                )
            case ManagedExpressions.LESS_THAN.value:
                assert self.less_than_value.data
                return LessThan(
                    question_id=question.id,
                    maximum_value=self.less_than_value.data,
                    inclusive=self.less_than_inclusive.data,
                )
            case ManagedExpressions.BETWEEN.value:
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
