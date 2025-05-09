from flask import current_app
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError


def validate_communities_gov_uk_email(form: FlaskForm, field: StringField) -> None:
    if field.data and "@" in field.data:
        internal_domains = current_app.config["INTERNAL_DOMAINS"]
        if not field.data.endswith(internal_domains):
            raise ValidationError(f"Email address must end with {' or '.join(internal_domains)}")


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
