from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput
from wtforms import RadioField, SubmitField
from wtforms.validators import Optional

# TODO: move all forms used by developer pages into this module. Add some linting rule that prevents any other parts
#       of the app importing from the developers package.


class PreviewCollectionForm(FlaskForm):
    submit = SubmitField("Preview this collection", widget=GovSubmitInput())


class CheckYourAnswersForm(FlaskForm):
    section_completed = RadioField(
        "Have you completed this section?",
        choices=[("yes", "Yes, I've completed this section"), ("no", "No, I'll come back to it later")],
        widget=GovRadioInput()
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())
