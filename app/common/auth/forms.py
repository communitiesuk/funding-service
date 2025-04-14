from urllib.parse import urlsplit

from flask import current_app, request, url_for
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError
from wtforms.widgets.core import HiddenInput


def validate_communities_gov_uk_email(form: FlaskForm, field: StringField) -> None:
    if field.data and "@" in field.data:
        if not field.data.endswith("@communities.gov.uk"):
            raise ValidationError("Email address must end with @communities.gov.uk")


def sanitise_redirect_url(url: str) -> str:
    safe_fallback_url = url_for("index")

    url_next = urlsplit(url)
    current_base_url = urlsplit(request.host_url)

    if (url_next.netloc or url_next.scheme) and url_next.netloc != current_base_url.netloc:
        current_app.logger.warning(
            "Attempt to redirect to unsafe URL %(bad_url)s; sanitised to %(safe_url)s",
            dict(bad_url=url, safe_url=safe_fallback_url),
        )
        return safe_fallback_url

    if url_next.scheme and url_next.scheme not in {"http", "https"}:
        current_app.logger.warning(
            "Attempt to redirect to URL with unexpected protocol %(bad_url)s; sanitised to %(safe_url)s",
            dict(bad_url=url, safe_url=safe_fallback_url),
        )
        return safe_fallback_url

    sanitised_url_next = url_next.path
    if url_next.query:
        sanitised_url_next += "?" + url_next.query

    return sanitised_url_next


class SignInForm(FlaskForm):
    redirect_to = StringField(widget=HiddenInput(), filters=[sanitise_redirect_url])
    email_address = StringField(
        "Email address",
        validators=[
            DataRequired(message="Enter your email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
            validate_communities_gov_uk_email,
        ],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Request a link", widget=GovSubmitInput())


class ClaimMagicLinkForm(FlaskForm):
    submit = SubmitField("Sign in", widget=GovSubmitInput())
