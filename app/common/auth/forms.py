from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email

from app.common.forms.validators import AccessGrantFundingEmail


class SignInForm(FlaskForm):
    email_address = StringField(
        "Email address",
        validators=[
            DataRequired(message="Enter your email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
            AccessGrantFundingEmail(),
        ],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Request sign in link", widget=GovSubmitInput())
