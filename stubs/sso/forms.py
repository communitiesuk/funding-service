from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError


def validate_communities_gov_uk_email(form: FlaskForm, field: StringField) -> None:
    if field.data and "@" in field.data:
        if not field.data.endswith("@communities.gov.uk"):
            raise ValidationError("Email address must end with @communities.gov.uk")


class SSOSignInForm(FlaskForm):
    email_address = StringField(
        "Email address",
        validators=[
            DataRequired(message="Enter your email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
            validate_communities_gov_uk_email,
        ],
        widget=GovTextInput(),
        filters=[lambda x: x.strip() if x else x],
    )
    submit = SubmitField("Sign in", widget=GovSubmitInput())
