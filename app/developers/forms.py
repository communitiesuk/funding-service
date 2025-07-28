from typing import TYPE_CHECKING

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSelect, GovSubmitInput
from wtforms import Field, SelectField, SubmitField, ValidationError
from wtforms.validators import DataRequired

from app.common.data.interfaces.collections import get_question_by_id, is_question_dependency_order_valid
from app.common.expressions.registry import get_supported_form_questions

if TYPE_CHECKING:
    from app.common.data.models import Question


# TODO: move all forms used by developer pages into this module. Add some linting rule that prevents any other parts
#       of the app importing from the developers package.
class ConfirmDeletionForm(FlaskForm):
    confirm_deletion = SubmitField("Confirm deletion", widget=GovSubmitInput())


class BecomeGrantTeamMemberForm(FlaskForm):
    submit = SubmitField("Become grant team member", widget=GovSubmitInput())


class ConditionSelectQuestionForm(FlaskForm):
    question = SelectField(
        "Which answer should the condition check?",
        choices=[],
        validators=[DataRequired("Select a question")],
        widget=GovSelect(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def __init__(self, *args, question: "Question", **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)

        self.target_question = question

        self.question.choices = [
            (question.id, f"{question.text} ({question.name})") for question in get_supported_form_questions(question)
        ]

    def validate_question(self: "ConditionSelectQuestionForm", field: "Field") -> None:
        depends_on_question = get_question_by_id(self.question.data)
        if not is_question_dependency_order_valid(self.target_question, depends_on_question):
            raise ValidationError("Select an answer that comes before this question in the form")
