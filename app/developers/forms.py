from typing import TYPE_CHECKING

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSelect, GovSubmitInput
from wtforms import RadioField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional

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
