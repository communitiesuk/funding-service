from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.models import Organisation
from app.common.forms.fields import MHCLGRadioInput


class DeclineSignOffForm(FlaskForm):
    decline_reason = StringField(
        "Why are you declining sign off?",
        widget=GovTextArea(),
        validators=[DataRequired("Enter a reason for declining sign off")],
    )

    submit = SubmitField("Decline sign off", widget=GovSubmitInput())


class EligibleOrganisationSelectionForm(FlaskForm):
    SIGN_UP_NEW_ORGANISATION_VALUE = "new_org"

    organisation = RadioField(
        "Select which organisation you are applying on behalf of:",
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
            item_hints.append({"hint": {"text": "Because you've accessed other grants with these organisations"}})
        for _ in domain_matched_orgs:
            item_hints.append({"hint": {"text": f"Because of your {email_domain} email"}})

        self.organisation.render_kw = {"params": {"items": item_hints}}
