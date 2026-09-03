from typing import Any

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
        ],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Sign in with link", widget=GovSubmitInput())

    def __init__(
        self, *args: Any, is_public_sign_in: bool = False, allow_invitations: bool = False, **kwargs: Any
    ) -> None:
        """
        If you're allowing users with invitations to pass through this form (ie new users without an account yet),
        it's important that the route handler claims those invitations and sets up permissions correctly.
        """
        super().__init__(*args, **kwargs)

        if not is_public_sign_in:
            # If not public sign in, we expect the user to exist in the system - or have a valid invitation
            self.email_address.validators = [
                *self.email_address.validators,
                AccessGrantFundingEmail(allow_invitations=allow_invitations),
            ]
