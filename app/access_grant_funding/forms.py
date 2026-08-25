from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email

from app.common.forms.filters import strip_string_if_not_empty


class DeclineSignOffForm(FlaskForm):
    decline_reason = StringField(
        "Why are you declining sign off?",
        widget=GovTextArea(),
        validators=[DataRequired("Enter a reason for declining sign off")],
    )

    submit = SubmitField("Decline sign off", widget=GovSubmitInput())


class AddGrantTeamMemberForm(FlaskForm):
    full_name = StringField(
        "Full name",
        widget=GovTextInput(),
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter the team member’s full name")],
    )
    email_address = StringField(
        "Email address",
        widget=GovTextInput(),
        filters=[strip_string_if_not_empty],
        validators=[
            DataRequired("Enter the team member’s email address"),
            Email("Enter an email address in the correct format, like name@example.com"),
        ],
    )

    submit = SubmitField("Confirm and add team member", widget=GovSubmitInput())
