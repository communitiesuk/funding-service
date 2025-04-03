from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import DataRequired


class GrantForm(FlaskForm):
    # TODO: we'll probably want this `strip` behaviour in a BaseForm which extends FlaskForm so that its consistent
    # we can use `bind_field` to apply that consistently
    name = StringField(
        "Grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Submit", widget=GovSubmitInput())
