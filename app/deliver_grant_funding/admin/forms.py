import csv
import datetime
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from flask import current_app
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovDateInput, GovSubmitInput, GovTextArea, GovTextInput
from markupsafe import Markup, escape
from wtforms import DateField, SubmitField
from wtforms.fields.choices import SelectField, SelectMultipleField
from wtforms.fields.simple import EmailField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional
from xgovuk_flask_admin import GovSelectWithSearch

from app.common.data.types import OrganisationData, OrganisationType

if TYPE_CHECKING:
    from app.common.data.models import Collection, Grant, GrantRecipient, Organisation
    from app.common.data.models_user import UserRole


class PlatformAdminSelectGrantForReportingLifecycleForm(FlaskForm):
    grant_id = SelectField(
        "Grant",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select a grant to view its reporting lifecycle")],
    )
    submit = SubmitField("Select grant", widget=GovSubmitInput())

    def __init__(self, grants: Sequence["Grant"]) -> None:
        super().__init__()

        self.grant_id.choices = [("", "")] + [(str(grant.id), grant.name) for grant in grants]  # type: ignore[assignment]


class PlatformAdminSelectReportForm(FlaskForm):
    collection_id = SelectField(
        "Monitoring report",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select a monitoring report to manage")],
    )
    submit = SubmitField("Select monitoring report", widget=GovSubmitInput())

    def __init__(self, collections: Sequence["Collection"]) -> None:
        super().__init__()

        self.collection_id.choices = [("", "")] + [(str(collection.id), collection.name) for collection in collections]  # type: ignore[assignment]


class PlatformAdminMakeGrantLiveForm(FlaskForm):
    submit = SubmitField("Make grant live", widget=GovSubmitInput())


class PlatformAdminMarkAsOnboardingForm(FlaskForm):
    submit = SubmitField("Mark as onboarding", widget=GovSubmitInput())


class PlatformAdminBulkCreateOrganisationsForm(FlaskForm):
    # The default structure of this data is set so that it should be easy to copy+paste from Delta's organisation export
    # when opened in Excel. Hide the irrelevant columns in Excel, then select the table contents and paste it into
    # the text box.
    organisations_data = TextAreaField(
        "Organisation TSV data",
        default="organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n",
        validators=[DataRequired()],
        widget=GovTextArea(),
    )
    submit = SubmitField("Set up organisations", widget=GovSubmitInput())

    def validate_organisations_data(self, field: TextAreaField) -> None:
        assert field.data

        if field.data.splitlines()[0] != "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date":
            field.errors.append(  # type: ignore[attr-defined]
                "The header row must be exactly: organisation-id\torganisation-name\ttype\tactive-date\tretirement-date"
            )

        try:
            self.get_normalised_organisation_data()
        except Exception as e:
            field.errors.append(f"The tab-separated data is not valid: {str(e)}")  # type: ignore[attr-defined]

    def get_normalised_organisation_data(self) -> list["OrganisationData"]:
        assert self.organisations_data.data
        organisations_data = self.organisations_data.data
        tsv_reader = csv.reader(organisations_data.splitlines(), delimiter="\t")
        _ = next(tsv_reader)  # Skip the header
        normalised_organisations = [
            OrganisationData(
                external_id=row[0],
                name=row[1],
                type=OrganisationType(row[2]),
                active_date=datetime.datetime.strptime(row[3], "%d/%m/%Y") if row[3] else None,
                retirement_date=datetime.datetime.strptime(row[4], "%d/%m/%Y") if row[4] else None,
            )
            for row in tsv_reader
        ]
        return normalised_organisations


class PlatformAdminCreateCertifiersForm(FlaskForm):
    certifiers_data = TextAreaField(
        "Certifiers TSV data",
        default="organisation-name\tfirst-name\tlast-name\temail-address\n",
        validators=[DataRequired()],
        widget=GovTextArea(),
    )
    submit = SubmitField("Set up certifiers", widget=GovSubmitInput())

    def __init__(self, organisations: Sequence["Organisation"]) -> None:
        super().__init__()
        self.organisations = organisations
        self.organisation_names_to_ids = {organisation.name: organisation.id for organisation in organisations}

    def validate_certifiers_data(self, field: TextAreaField) -> None:
        assert field.data

        if field.data.splitlines()[0] != "organisation-name\tfirst-name\tlast-name\temail-address":
            field.errors.append(  # type: ignore[attr-defined]
                "The header row must be exactly: organisation-name\tfirst-name\tlast-name\temail-address"
            )
            return

        try:
            certifiers_data = self.get_normalised_certifiers_data()
        except Exception as e:
            field.errors.append(f"The tab-separated data is not valid: {str(e)}")  # type: ignore[attr-defined]
            return

        # Validate all organisation names first before creating any users
        invalid_orgs = []
        for org_name, _, _ in certifiers_data:
            if org_name not in self.organisation_names_to_ids:
                invalid_orgs.append(org_name)

        if invalid_orgs:
            unique_invalid_orgs = sorted(set(invalid_orgs))
            for org_name in unique_invalid_orgs:
                field.errors.append(  # type: ignore[attr-defined]
                    f"Organisation '{org_name}' has not been set up in Deliver grant funding."
                )

        # Validate email addresses
        from wtforms.validators import Email as EmailValidator

        email_validator = EmailValidator()
        invalid_emails = []
        for _, _, email_address in certifiers_data:
            try:
                email_validator(self, type("obj", (), {"data": email_address})())
            except Exception:
                invalid_emails.append(email_address)

        if invalid_emails:
            field.errors.append(  # type: ignore[attr-defined]
                f"Invalid email address(es): {', '.join(invalid_emails)}"
            )

    def get_normalised_certifiers_data(self) -> list[tuple[str, str, str]]:
        assert self.certifiers_data.data
        users_data = self.certifiers_data.data
        tsv_reader = csv.reader(users_data.splitlines(), delimiter="\t")
        _ = next(tsv_reader)  # Skip the header
        normalised_users = [(row[0], row[1] + " " + row[2], row[3]) for row in tsv_reader]
        return normalised_users


class PlatformAdminBulkCreateGrantRecipientsForm(FlaskForm):
    recipients = SelectMultipleField(
        "Grant recipients", choices=[], widget=GovSelectWithSearch(multiple=True), validators=[DataRequired()]
    )

    submit = SubmitField("Set up grant recipients", widget=GovSubmitInput())

    def __init__(
        self, organisations: Sequence["Organisation"], existing_grant_recipients: Sequence["GrantRecipient"]
    ) -> None:
        super().__init__()
        existing_grant_recipient_org_ids = {gr.organisation.id for gr in existing_grant_recipients}
        self.recipients.choices = [
            (str(org.id), org.name) for org in organisations if org.id not in existing_grant_recipient_org_ids
        ]


class PlatformAdminCreateGrantRecipientUserForm(FlaskForm):
    users_data = TextAreaField(
        "Grant recipient users TSV data",
        default="organisation-name\tfull-name\temail-address\n",
        validators=[DataRequired()],
        widget=GovTextArea(),
    )
    submit = SubmitField("Set up grant recipient users", widget=GovSubmitInput())

    def __init__(self, grant_recipients: Sequence["GrantRecipient"]) -> None:
        super().__init__()
        self.grant_recipients = grant_recipients

        self.users_data.description = Markup(
            "<span>Copy and paste the 'Funding service ingest' table from the "
            "<a class='govuk-link govuk-link--no-visited-state' "
            f"href='{escape(current_app.config['GRANT_TEAM_RECIPIENT_LIST_SPREADSHEET'])}' target='_blank'>"
            "grant team's completed version of the recipient spreadsheet (opens in a new tab)"
            "</a></span>"
        )

    def validate_users_data(self, field: TextAreaField) -> None:
        assert field.data

        if field.data.splitlines()[0] != "organisation-name\tfull-name\temail-address":
            field.errors.append(  # type: ignore[attr-defined]
                "The header row must be exactly: organisation-name\tfull-name\temail-address"
            )
            return

        try:
            users_data = self.get_normalised_users_data()
        except Exception as e:
            field.errors.append(f"The tab-separated data is not valid: {str(e)}")  # type: ignore[attr-defined]
            return

        # Validate email addresses
        from wtforms.validators import Email as EmailValidator

        email_validator = EmailValidator()
        invalid_emails = []
        for _, _, email_address in users_data:
            try:
                email_validator(self, type("obj", (), {"data": email_address})())
            except Exception:
                invalid_emails.append(email_address)

        if invalid_emails:
            field.errors.append(  # type: ignore[attr-defined]
                f"Invalid email address(es): {', '.join(invalid_emails)}"
            )

    def get_normalised_users_data(self) -> list[tuple[str, str, str]]:
        assert self.users_data.data
        users_data = self.users_data.data
        tsv_reader = csv.reader(users_data.splitlines(), delimiter="\t")
        _ = next(tsv_reader)  # Skip the header
        normalised_users = [(row[0], row[1], row[2]) for row in tsv_reader]
        return normalised_users


class PlatformAdminRevokeGrantRecipientUsersForm(FlaskForm):
    user_roles = SelectMultipleField(
        "Grant recipient users to revoke",
        choices=[],
        widget=GovSelectWithSearch(multiple=True),
        validators=[DataRequired()],
    )
    submit = SubmitField("Revoke access", widget=GovSubmitInput())

    def __init__(self, user_roles: Sequence["UserRole"]) -> None:
        super().__init__()
        self.user_roles.choices = [
            (
                f"{user_role.user_id}|{user_role.organisation_id}",
                f"{user_role.user.name} ({user_role.user.email}) - {user_role.organisation.name}",
            )
            for user_role in user_roles
        ]


class PlatformAdminRevokeCertifiersForm(FlaskForm):
    organisation_id = SelectField(
        "Organisation",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select an organisation")],
    )
    email = EmailField(
        "Email address",
        validators=[DataRequired("Enter an email address"), Email("Enter a valid email address")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Revoke certifier access", widget=GovSubmitInput())

    def __init__(self, organisations: Sequence["Organisation"]) -> None:
        super().__init__()
        self.organisation_id.choices = [("", "")] + [(str(org.id), org.name) for org in organisations]  # type: ignore[assignment]


class PlatformAdminSetCollectionDatesForm(FlaskForm):
    reporting_period_start_date = DateField(
        "Reporting period start date",
        validators=[Optional()],
        widget=GovDateInput(),
        format=["%d %m %Y", "%d %b %Y", "%d %B %Y"],
    )
    reporting_period_end_date = DateField(
        "Reporting period end date",
        validators=[Optional()],
        widget=GovDateInput(),
        format=["%d %m %Y", "%d %b %Y", "%d %B %Y"],
    )
    submission_period_start_date = DateField(
        "Submission period start date",
        validators=[Optional()],
        widget=GovDateInput(),
        format=["%d %m %Y", "%d %b %Y", "%d %B %Y"],
    )
    submission_period_end_date = DateField(
        "Submission period end date",
        validators=[Optional()],
        widget=GovDateInput(),
        format=["%d %m %Y", "%d %b %Y", "%d %B %Y"],
    )
    submit = SubmitField("Save dates", widget=GovSubmitInput())

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        result: bool = super().validate(extra_validators)

        if (self.reporting_period_start_date.data or self.reporting_period_end_date.data) and not (
            self.reporting_period_start_date.data and self.reporting_period_end_date.data
        ):
            self.reporting_period_start_date.errors.append("Set both a reporting start and end date, or neither")  # type: ignore[attr-defined]
            self.reporting_period_end_date.errors.append("Set both a reporting start and end date, or neither")  # type: ignore[attr-defined]
            return False

        if (self.submission_period_start_date.data or self.submission_period_end_date.data) and not (
            self.submission_period_start_date.data and self.submission_period_end_date.data
        ):
            self.submission_period_start_date.errors.append("Set both a submission start and end date, or neither")  # type: ignore[attr-defined]
            self.submission_period_end_date.errors.append("Set both a submission start and end date, or neither")  # type: ignore[attr-defined]
            return False

        if self.reporting_period_start_date.data and self.reporting_period_end_date.data:
            if self.reporting_period_start_date.data >= self.reporting_period_end_date.data:
                self.reporting_period_start_date.errors.append(  # type: ignore[attr-defined]
                    "report period start date must be before reporting period end date"
                )
                self.reporting_period_end_date.errors.append(  # type: ignore[attr-defined]
                    "report period end date must be after reporting period start date"
                )
                return False

        if self.submission_period_start_date.data and self.submission_period_end_date.data:
            if self.submission_period_start_date.data >= self.submission_period_end_date.data:
                self.submission_period_start_date.errors.append(  # type: ignore[attr-defined]
                    "Submission period start date must be before submission period end date"
                )
                self.submission_period_end_date.errors.append(  # type: ignore[attr-defined]
                    "Submission period start date must be before submission period end date"
                )
                return False

        if self.reporting_period_end_date.data and self.submission_period_start_date.data:
            if self.reporting_period_end_date.data >= self.submission_period_start_date.data:
                self.reporting_period_end_date.errors.append(  # type: ignore[attr-defined]
                    "Report period end date must be before submission period start date"
                )
                self.submission_period_start_date.errors.append(  # type: ignore[attr-defined]
                    "Report period end date must be before submission period start date"
                )
                return False

        return result


class PlatformAdminScheduleReportForm(FlaskForm):
    submit = SubmitField("Sign off and lock report", widget=GovSubmitInput())
