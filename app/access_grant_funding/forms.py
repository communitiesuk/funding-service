from collections.abc import Callable
from typing import Any

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError

from app.access_grant_funding.mock_registries import RegisteredOrganisation
from app.access_grant_funding.session_models import SignUpOrganisationType


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


class PublicSignUpOrganisationTypeForm(FlaskForm):
    organisation_type = RadioField(
        "What is your organisation type?",
        choices=[
            (SignUpOrganisationType.COMPANY.value, "Company"),
            (SignUpOrganisationType.CHARITY.value, "Charity"),
            (SignUpOrganisationType.LOCAL_AUTHORITY.value, "Local authority"),
            (SignUpOrganisationType.OTHER.value, "Other"),
        ],
        validators=[DataRequired(message="Select your organisation type")],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class PublicSignUpOrganisationReferenceForm(FlaskForm):
    has_reference_number = RadioField(
        "Do you have a reference number?",
        choices=[("yes", "Yes"), ("no", "No")],
        validators=[DataRequired(message="Select an option")],
        widget=GovRadioInput(),
    )
    reference_number = StringField(
        "Reference number",
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def __init__(
        self,
        *args: Any,
        lookup: Callable[[str], RegisteredOrganisation | None],
        registry_label: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._lookup = lookup
        self.registry_label = registry_label
        self.has_reference_number.label.text = f"Do you have a {registry_label} reference number?"
        self.reference_number.label.text = f"{registry_label} reference number"

    def validate_reference_number(self, field: StringField) -> None:
        if self.has_reference_number.data != "yes":
            return

        if not field.data:
            raise ValidationError(f"Enter your {self.registry_label} reference number")

        if self._lookup(field.data) is None:
            raise ValidationError(
                f"We could not find that {self.registry_label} reference number. Check it and try again."
            )


class PublicSignUpOrganisationNameForm(FlaskForm):
    organisation_name = StringField(
        "What is the name of your organisation?",
        validators=[DataRequired(message="Enter the name of your organisation")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class PublicSignUpConfirmOrganisationForm(FlaskForm):
    is_correct_organisation = RadioField(
        "Is this the organisation you're applying on behalf of?",
        choices=[("yes", "Yes"), ("no", "No")],
        validators=[DataRequired(message="Select an option")],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class DeclineSignOffForm(FlaskForm):
    decline_reason = StringField(
        "Why are you declining sign off?",
        widget=GovTextArea(),
        validators=[DataRequired("Enter a reason for declining sign off")],
    )

    submit = SubmitField("Decline sign off", widget=GovSubmitInput())
