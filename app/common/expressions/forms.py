from typing import Any, Mapping, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextInput
from wtforms import IntegerField, RadioField, SubmitField
from wtforms.validators import DataRequired, Optional

from app.common.data.types import ManagedExpressions


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


class AddNumberValidationForm(FlaskForm):
    type = RadioField(
        "",
        choices=[(ManagedExpressions.GREATER_THAN, ManagedExpressions.GREATER_THAN.value)],
        validators=[DataRequired("Select the kind of validation to apply")],
        widget=GovRadioInput(),
    )

    value = IntegerField("Value", widget=GovTextInput(), validators=[Optional()])

    submit = SubmitField("Add validation", widget=GovSubmitInput())

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        if self.type.data:
            self.value.validators = [DataRequired("Enter the minimum value allowed for this question")]

        # fixme: IDE realises this is a FlaskForm and bool but mypy is calling it "Any" on pre-commit
        return super().validate(extra_validators=extra_validators)  # type: ignore
