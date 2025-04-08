from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError


def validate_communities_gov_uk_email(form: FlaskForm, field: StringField) -> None:
    if field.data and "@" in field.data:
        if not field.data.endswith("@communities.gov.uk"):
            raise ValidationError("Email address must end with @communities.gov.uk")


class SignInForm(FlaskForm):
    email_address = StringField(
        "Request a link to sign in",
        validators=[
            DataRequired(message="Request a link to sign in"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
            validate_communities_gov_uk_email,
        ],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Request a link", widget=GovSubmitInput())
