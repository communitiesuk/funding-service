from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import DataRequired


class GrantForm(FlaskForm):
    name = StringField(
        "Grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())
