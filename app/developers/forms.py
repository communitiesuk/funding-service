from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.fields.numeric import IntegerField
from wtforms.validators import DataRequired, NumberRange

# TODO: move all forms used by developer pages into this module. Add some linting rule that prevents any other parts
#       of the app importing from the developers package.


class PreviewCollectionForm(FlaskForm):
    submit = SubmitField("Preview this collection", widget=GovSubmitInput())


class SeedGrantForm(FlaskForm):
    grant_name = StringField("Grant name", validators=[DataRequired()], widget=GovTextInput())
    min_sections = IntegerField(
        "Minimum number of sections",
        default=3,
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        widget=GovTextInput(),
    )
    max_sections = IntegerField(
        "Minimum number of sections",
        default=10,
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        widget=GovTextInput(),
    )
    min_forms = IntegerField(
        "Minimum number of forms per section",
        default=3,
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        widget=GovTextInput(),
    )
    max_forms = IntegerField(
        "Minimum number of forms per section",
        default=10,
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        widget=GovTextInput(),
    )
    min_questions = IntegerField(
        "Minimum number of questions per form",
        default=3,
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        widget=GovTextInput(),
    )
    max_questions = IntegerField(
        "Minimum number of questions per form",
        default=10,
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        widget=GovTextInput(),
    )
    submit = SubmitField("Seed a grant", widget=GovSubmitInput())
