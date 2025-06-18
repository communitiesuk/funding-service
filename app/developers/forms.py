from typing import TYPE_CHECKING, Any, Mapping, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSelect, GovSubmitInput, GovTextInput
from wtforms import IntegerField, RadioField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional

from app.common.expressions.managed import ManagedExpressions

if TYPE_CHECKING:
    from app.common.data.models import Question

# TODO: move all forms used by developer pages into this module. Add some linting rule that prevents any other parts
#       of the app importing from the developers package.


class PreviewCollectionForm(FlaskForm):
    submit = SubmitField("Test this collection", widget=GovSubmitInput())


class CheckYourAnswersForm(FlaskForm):
    section_completed = RadioField(
        "Have you completed this section?",
        choices=[("yes", "Yes, I’ve completed this section"), ("no", "No, I’ll come back to it later")],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())

    # the form should be validly optional unless all questions in the section have been answered
    def set_is_required(self, all_questions_answered: bool) -> None:
        if all_questions_answered:
            self.section_completed.validators = [DataRequired("Select if you have completed this section")]
        else:
            self.section_completed.validators = [Optional()]


class ConfirmDeletionForm(FlaskForm):
    confirm_deletion = SubmitField("Confirm deletion", widget=GovSubmitInput())


class SubmitSubmissionForm(FlaskForm):
    submit = SubmitField("Submit", widget=GovSubmitInput())


class ConditionSelectQuestionForm(FlaskForm):
    question = SelectField(
        "Which answer should the condition check?",
        choices=[],
        validators=[DataRequired("Select a question")],
        widget=GovSelect(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def add_question_options(self, questions: list["Question"]) -> None:
        self.question.choices = [(question.id, f"{question.text} ({question.name})") for question in questions]


class AddNumberConditionForm(FlaskForm):
    # todo: should any condition or validation be able to override the human readable message I suspect so
    type = RadioField(
        "Only show the question if the answer is",
        choices=[(ManagedExpressions.GREATER_THAN, ManagedExpressions.GREATER_THAN.value)],
        validators=[DataRequired("Select what the answer should be to show this question")],
        widget=GovRadioInput(),
    )
    value = IntegerField("Value", widget=GovTextInput(), validators=[Optional()])

    submit = SubmitField("Add condition", widget=GovSubmitInput())

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        # fixme: only validate the value if the type has been set, there's probably
        #        a better way to do this
        if self.type.data:
            self.value.validators = [DataRequired("Enter a value")]

        # fixme: IDE realises this is a FlaskForm and bool but mypy is calling it "Any" on pre-commit
        return super().validate(extra_validators=extra_validators)  # type: ignore
