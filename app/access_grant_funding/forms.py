from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email


class PublicSignUpEmailForm(FlaskForm):
    # NOTE: deliberately does not use the `AccessGrantFundingEmail` validator that `SignInForm` uses; people signing up
    # through a public page do not have access to the service yet, which is the whole point of them being here.
    email_address = StringField(
        "Enter your work email address",
        description="You'll need to verify your email address - we'll only use it if you are eligible to apply",
        validators=[
            DataRequired(message="Enter your work email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
        ],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class PublicSignUpNameForm(FlaskForm):
    full_name = StringField(
        "What is your full name?",
        validators=[DataRequired(message="Enter your full name")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue and start application", widget=GovSubmitInput())


class DeclineSignOffForm(FlaskForm):
    decline_reason = StringField(
        "Why are you declining sign off?",
        widget=GovTextArea(),
        validators=[DataRequired("Enter a reason for declining sign off")],
    )

    submit = SubmitField("Decline sign off", widget=GovSubmitInput())
