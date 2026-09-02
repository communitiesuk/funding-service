from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, Email

from app.access_grant_funding.session_models import SignUpOrganisationType
from app.common.data.models import Organisation
from app.common.forms.fields import MHCLGRadioInput
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


class EligibleOrganisationSelectionForm(FlaskForm):
    SIGN_UP_NEW_ORGANISATION_VALUE = "new_org"

    organisation = RadioField(
        "Which organisation are you applying on behalf of?",
        choices=[],
        widget=MHCLGRadioInput(insert_divider_before_last_item=True),
        validators=[DataRequired("Select an organisation to continue")],
    )
    submit = SubmitField(widget=GovSubmitInput())

    def __init__(
        self,
        role_matched_orgs: list[Organisation],
        domain_matched_orgs: list[Organisation],
        email_domain: str,
    ) -> None:
        super().__init__()

        # Add the Sign up a new organisaion option at the end
        self.organisation.choices = [(str(org.id), org.name) for org in [*role_matched_orgs, *domain_matched_orgs]] + [
            (self.SIGN_UP_NEW_ORGANISATION_VALUE, "Sign up a new organisation to apply")
        ]

        item_hints: list[dict] = []
        for _ in role_matched_orgs:
            item_hints.append({"hint": {"text": "Based on your access to other grants"}})
        for _ in domain_matched_orgs:
            item_hints.append({"hint": {"text": f"Based on your {email_domain} email"}})

        self.organisation.render_kw = {
            "params": {
                "items": item_hints,
                "fieldset": {
                    "legend": {
                        "text": self.organisation.label.text,
                        "classes": "govuk-fieldset__legend--m",
                    }
                },
            }
        }


class CreateOrganisationTypeForm(FlaskForm):
    organisation_type = RadioField(
        "What is your organisation type?",
        choices=[
            (SignUpOrganisationType.COMPANY.value, SignUpOrganisationType.COMPANY.label),
            (SignUpOrganisationType.CHARITY.value, SignUpOrganisationType.CHARITY.label),
            (SignUpOrganisationType.LOCAL_AUTHORITY.value, SignUpOrganisationType.LOCAL_AUTHORITY.label),
            (SignUpOrganisationType.OTHER.value, SignUpOrganisationType.OTHER.label),
        ],
        widget=GovRadioInput(),
        validators=[DataRequired("Select your organisation type")],
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class CreateOrganisationUserNameForm(FlaskForm):
    user_name = StringField(
        "What is your full name?",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter your full name")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class CreateOrganisationNameForm(FlaskForm):
    name = StringField(
        "What is the name of your organisation?",
        description="Enter the official registered name of your organisation",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter the name of your organisation")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())
