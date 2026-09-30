import re
from typing import Any, NamedTuple

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from wtforms import HiddenField, RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError

from app.access_grant_funding.session_models import CharityRegulator, SignUpOrganisationType
from app.common.data.models import Organisation
from app.common.forms.fields import MHCLGRadioInput
from app.common.forms.filters import strip_string_if_not_empty
from app.common.helpers.charities import (
    ENGLAND_AND_WALES_CHARITY_NUMBER,
    NORTHERN_IRELAND_CHARITY_NUMBER,
    SCOTLAND_CHARITY_NUMBER,
    clean_charity_number,
)
from app.extensions import companies_house_service
from app.services.companies_house import normalize_company_number


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
        invite_matched_orgs: list[Organisation],
        role_matched_orgs: list[Organisation],
        domain_matched_orgs: list[Organisation],
        email_domain: str,
    ) -> None:
        super().__init__()

        # Add the Sign up a new organisaion option at the end
        self.organisation.choices = [
            (str(org.id), org.name) for org in [*invite_matched_orgs, *role_matched_orgs, *domain_matched_orgs]
        ] + [(self.SIGN_UP_NEW_ORGANISATION_VALUE, "Apply on behalf of another organisation")]

        item_hints: list[dict] = []
        for _ in invite_matched_orgs:
            item_hints.append({"hint": {"text": "Based on an open invite to this organisation"}})
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


class UserNameForm(FlaskForm):
    """Shared by both matched existing org and set up org in the public sign up journey."""

    user_name = StringField(
        "What is your full name?",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter your full name")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class CreateOrganisationCompanyNumberForm(FlaskForm):
    company_number = StringField(
        "What is your company number?",
        description="Company number is usually 8 characters long",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter your company number")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def validate_company_number(self, field: StringField) -> None:
        assert field.data is not None
        try:
            field.data = normalize_company_number(field.data)
        except ValueError as e:
            raise ValidationError("Company number must be 8 characters, made up of letters and numbers") from e


class CreateOrganisationCharityRegulatorForm(FlaskForm):
    charity_regulator = RadioField(
        "Where is your charity registered?",
        choices=[(regulator.value, regulator.label) for regulator in CharityRegulator],
        widget=MHCLGRadioInput(insert_divider_before_last_item=True),
        validators=[DataRequired("Select where your charity is registered")],
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class CharityNumberFormat(NamedTuple):
    hint: str
    pattern: re.Pattern[str]
    error: str
    register_url_config_key: str
    prefix: str = ""  # part of every number on the register, so shown in front of the input, not typed


CHARITY_NUMBER_FORMATS = {
    CharityRegulator.ENGLAND_AND_WALES: CharityNumberFormat(
        hint="This is 6 or 7 numbers.",
        pattern=ENGLAND_AND_WALES_CHARITY_NUMBER,
        error="Charity number must be 6 or 7 numbers, for example, 123456 or 1234567",
        register_url_config_key="CHARITY_COMMISSION_URL",
    ),
    CharityRegulator.SCOTLAND: CharityNumberFormat(
        hint="This is 8 characters in total and starts with SC0, for example, SC012345.",
        pattern=SCOTLAND_CHARITY_NUMBER,
        error="Charity number must be 8 characters starting with SC0, for example, SC012345",
        register_url_config_key="SCOTTISH_CHARITY_REGULATOR_URL",
    ),
    CharityRegulator.NORTHERN_IRELAND: CharityNumberFormat(
        hint="This is NIC followed by 6 numbers, for example, NIC123456.",
        pattern=NORTHERN_IRELAND_CHARITY_NUMBER,
        error="Charity number must be 6 numbers, for example, 123456",
        register_url_config_key="CHARITY_COMMISSION_NI_URL",
        prefix="NIC",
    ),
}


class CreateOrganisationCharityNumberForm(FlaskForm):
    charity_number = StringField(
        "What is your charity number?",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter your charity number")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def __init__(self, charity_regulator: CharityRegulator, charity_number: str | None) -> None:
        self.number_format = CHARITY_NUMBER_FORMATS[charity_regulator]
        super().__init__(
            charity_number=charity_number.removeprefix(self.number_format.prefix) if charity_number else None
        )

    def validate_charity_number(self, field: StringField) -> None:
        assert field.data is not None
        prefix = self.number_format.prefix
        charity_number = prefix + clean_charity_number(field.data).removeprefix(prefix)
        if not self.number_format.pattern.fullmatch(charity_number):
            raise ValidationError(self.number_format.error)
        field.data = charity_number


class CreateOrganisationNameForm(FlaskForm):
    name = StringField(
        "What is the name of your organisation?",
        description="Enter the official registered name of your organisation",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter the name of your organisation")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class CompaniesHouseSearchForm(FlaskForm):
    q = StringField(
        "Search Companies House register",
        description="Search by company name or number",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter a company name or number")],
        widget=GovTextInput(),
    )

    def validate_q(self, field: StringField) -> None:
        assert field.data is not None
        min_length = companies_house_service.min_query_length
        max_length = companies_house_service.max_query_length
        if len(field.data) < min_length:
            raise ValidationError(f"Company name or number must be {min_length} characters or more")
        if len(field.data) > max_length:
            raise ValidationError(f"Company name or number must be {max_length} characters or fewer")


class CompaniesHouseSelectForm(FlaskForm):
    # not rendered as an input: each result row's Select button submits its company number as this field's value
    company_number = StringField(validators=[DataRequired()])


class CompaniesHouseUnavailableForm(FlaskForm):
    add_manually = RadioField(
        "Do you want to add your organisation manually?",
        choices=[(True, "Yes"), (False, "No, I'll try again later")],
        validators=[DataRequired("Select yes if you want to add your organisation manually")],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class CompaniesHouseSwitchToManualForm(FlaskForm):
    mode = HiddenField("", validators=[DataRequired()])
    submit = SubmitField("add your organisation manually")


class CreateOrganisationAllowTeamMembersForm(FlaskForm):
    allow_team_members = RadioField(
        choices=[(True, "Yes"), (False, "No")],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def __init__(self, *args: Any, organisation_name: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.allow_team_members.label.text = (
            f"Do you want to allow team members to apply as {organisation_name} in the future?"
        )
        self.allow_team_members.validators = [
            DataRequired(f"Select yes if you want to allow team members to apply as {organisation_name}")
        ]
