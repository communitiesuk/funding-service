from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovCheckboxInput, GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.fields.simple import BooleanField
from wtforms.validators import DataRequired

from app.common.forms.validators import CommunitiesEmail


class SSOSignInForm(FlaskForm):
    email_address = StringField(
        "Email address",
        validators=[
            DataRequired(message="Enter your email address"),
            CommunitiesEmail(),
        ],
        widget=GovTextInput(),
        filters=[lambda x: x.strip() if x else x],
    )
    is_member = BooleanField(
        "Member type login",
        widget=GovCheckboxInput(),
    )
    submit = SubmitField("Sign in", widget=GovSubmitInput())
