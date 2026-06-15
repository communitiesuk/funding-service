import csv
import datetime
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

import email_validator
from flask import current_app, flash
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovCheckboxesInput,
    GovCheckboxInput,
    GovDateInput,
    GovRadioInput,
    GovSubmitInput,
    GovTextArea,
    GovTextInput,
)
from markupsafe import Markup, escape
from wtforms import DateField, RadioField, SubmitField
from wtforms.fields.choices import SelectField, SelectMultipleField
from wtforms.fields.simple import BooleanField, EmailField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional
from xgovuk_flask_admin import GovSelectWithSearch

from app.common.data.types import (
    GrantRecipientStatusEnum,
    OrganisationData,
    OrganisationType,
    TraceLevelEnum,
)
from app.common.helpers.request_tracing import REQUEST_TRACING_TTL
from app.common.utils import uppercase_first

if TYPE_CHECKING:
    from app.common.data.models import Collection, Grant, GrantRecipient, Organisation
    from app.common.data.models_user import User


class PlatformAdminSelectGrantForCollectionLifecycleForm(FlaskForm):
    grant_id = SelectField(
        "Grant",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select a grant to view its collection lifecycle")],
    )
    submit = SubmitField("Select grant", widget=GovSubmitInput())

    def __init__(self, grants: Sequence[Grant]) -> None:
        super().__init__()

        self.grant_id.choices = [("", "")] + [(str(grant.id), grant.name) for grant in grants]


class PlatformAdminSelectCollectionForm(FlaskForm):
    collection_id = SelectField(
        "Collection",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select a collection to manage")],
    )
    submit = SubmitField("Select collection", widget=GovSubmitInput())

    def __init__(self, collections: Sequence[Collection]) -> None:
        super().__init__()

        choices = [("", "")]
        for collection in collections:
            label = f"{collection.name} ({collection.type.value})"
            choices.append((str(collection.id), label))

        self.collection_id.choices = choices


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

    def get_normalised_organisation_data(self) -> list[OrganisationData]:
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

    def __init__(self, organisations: Sequence[Organisation]) -> None:
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
                flash(f"Ignoring certifier for '{org_name}' - organisation has not been set up.", "error")

        # Validate email addresses
        invalid_emails = []
        for _, _, email_address in certifiers_data:
            try:
                email_validator.validate_email(email_address, check_deliverability=False, allow_smtputf8=True)
                if "’" in email_address:
                    raise email_validator.EmailNotValidError("Email addresses cannot contain smart quotes")
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
    status = RadioField(
        "Grant recipient status",
        choices=[(s.value, s.value.capitalize()) for s in GrantRecipientStatusEnum],
        validators=[DataRequired()],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Set up grant recipients", widget=GovSubmitInput())

    def __init__(
        self, organisations: Sequence[Organisation], existing_grant_recipients: Sequence[GrantRecipient]
    ) -> None:
        super().__init__()
        existing_grant_recipient_org_ids = {gr.organisation.id for gr in existing_grant_recipients}
        self.recipients.choices = [
            (str(org.id), org.name) for org in organisations if org.id not in existing_grant_recipient_org_ids
        ]


class PlatformAdminCreateGrantRecipientDataProvidersForm(FlaskForm):
    users_data = TextAreaField(
        "Grant recipient data providers TSV data",
        default="organisation-name\tfull-name\temail-address\n",
        validators=[DataRequired()],
        widget=GovTextArea(),
    )
    submit = SubmitField("Set up data providers", widget=GovSubmitInput())

    def __init__(self, grant_recipients: Sequence[GrantRecipient]) -> None:
        super().__init__()
        self.grant_recipients = grant_recipients
        self.organisation_names_to_ids = {
            grant_recipient.organisation.name: grant_recipient.organisation_id for grant_recipient in grant_recipients
        }

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

        # Validate all organisation names first before creating any users
        invalid_orgs = []
        for org_name, *_ in users_data:
            if org_name not in self.organisation_names_to_ids:
                invalid_orgs.append(org_name)

        if invalid_orgs:
            unique_invalid_orgs = sorted(set(invalid_orgs))
            for org_name in unique_invalid_orgs:
                field.errors.append(  # type: ignore[attr-defined]
                    f"Organisation '{org_name}' is not a grant recipient for this grant."
                )

        # Validate email addresses
        invalid_emails = []
        for _, _, email_address in users_data:
            try:
                email_validator.validate_email(email_address, check_deliverability=False, allow_smtputf8=True)
                if "’" in email_address:
                    raise email_validator.EmailNotValidError("Email addresses cannot contain smart quotes")
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


class PlatformAdminAddSingleDataProviderForm(FlaskForm):
    grant_recipient = SelectField(
        "Grant recipient",
        choices=[],
        validators=[DataRequired("Select a grant recipient")],
        widget=GovSelectWithSearch(),
    )
    full_name = StringField(
        "Full name",
        validators=[DataRequired("Enter the data provider's full name")],
        widget=GovTextInput(),
    )
    email_address = StringField(
        "Email address",
        validators=[DataRequired("Enter the data provider's email address"), Email()],
        widget=GovTextInput(),
    )
    send_notification_email = BooleanField(
        "Send 'submission is ready to complete' email",
        description="",
        widget=GovCheckboxInput(),
    )
    submit = SubmitField("Add data provider", widget=GovSubmitInput())

    def __init__(
        self, collection: Collection, grant_recipients: Sequence[GrantRecipient], *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.grant_recipients = grant_recipients
        self.grant_recipient.choices = [("", "")] + [(str(gr.id), gr.organisation.name) for gr in grant_recipients]
        self.send_notification_email.description = (
            "Send an email to notify the data provider that the "
            f"{collection.type.constants.singular} is open for submissions."
        )


class PlatformAdminAddTestGrantRecipientUserForm(FlaskForm):
    grant_recipient = SelectField(
        "Test grant recipient",
        choices=[],
        validators=[DataRequired("Select a test grant recipient")],
        widget=GovSelectWithSearch(),
    )

    mhclg_user = SelectField(
        "MHCLG users",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select an MHCLG user")],
    )

    submit = SubmitField("Add user", widget=GovSubmitInput())

    def __init__(
        self,
        grant_recipients: Sequence[GrantRecipient],
        mhclg_users: list[User],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        # Populate grant recipient choices
        self.grant_recipient.choices = [("", "")] + [(str(gr.id), gr.organisation.name) for gr in grant_recipients]

        self.mhclg_user.choices = [("", "")] + [(str(user.id), f"{user.name} ({user.email})") for user in mhclg_users]


class PlatformAdminRevokeGrantRecipientUsersForm(FlaskForm):
    grant_recipients_data_providers = SelectMultipleField(
        "Grant recipient data providers to revoke",
        choices=[],
        widget=GovSelectWithSearch(multiple=True),
        validators=[DataRequired()],
    )
    submit = SubmitField("Revoke access", widget=GovSubmitInput())

    def __init__(self, grant_recipients_data_providers: Mapping[GrantRecipient, Sequence[User]]) -> None:
        super().__init__()
        self.grant_recipients_data_providers.choices = [
            (
                f"{data_provider.id}|{grant_recipient.organisation_id}",
                f"{data_provider.name} ({data_provider.email}) - {grant_recipient.organisation.name}",
            )
            for grant_recipient, data_providers in grant_recipients_data_providers.items()
            for data_provider in data_providers
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

    def __init__(self, organisations: Sequence[Organisation]) -> None:
        super().__init__()
        self.organisation_id.choices = [("", "")] + [(str(org.id), org.name) for org in organisations]


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
    submit = SubmitField("Sign off and lock collection", widget=GovSubmitInput())


class PlatformAdminMakeReportLiveForm(FlaskForm):
    confirm_grant_recipients = BooleanField(
        validators=[DataRequired("Confirm the number of grant recipients")], widget=GovCheckboxInput()
    )
    confirm_grant_recipient_users = BooleanField(
        validators=[DataRequired("Confirm the number of grant recipient users")], widget=GovCheckboxInput()
    )
    confirm_privacy_policy = BooleanField(
        "The privacy policy has been set up",
        validators=[DataRequired("Confirm the privacy policy has been set up")],
        widget=GovCheckboxInput(),
    )
    confirm_certification = BooleanField(
        validators=[DataRequired("Confirm the certification setting")], widget=GovCheckboxInput()
    )
    confirm_submission_dates = BooleanField(
        validators=[DataRequired("Confirm the submission dates")], widget=GovCheckboxInput()
    )
    confirm_multiple_submissions = BooleanField(
        validators=[DataRequired("Confirm the multiple submissions setting")], widget=GovCheckboxInput()
    )
    confirm_managed_by_service = BooleanField(
        validators=[DataRequired("Confirm the managed by service setting")], widget=GovCheckboxInput()
    )
    confirm_managed_submissions_count = BooleanField(
        validators=[DataRequired("Confirm the number of managed submissions")], widget=GovCheckboxInput()
    )
    submit = SubmitField("Open collection for submissions", widget=GovSubmitInput())

    def __init__(
        self,
        collection: "Collection",
        grant_recipients_count: int,
        data_providers_count: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        from app.common.filters import format_date_short

        bold = 'class="govuk-!-font-weight-bold"'
        self.confirm_grant_recipients.label.text = Markup(
            f"It is correct that this grant has <strong {bold}>"
            f"{grant_recipients_count} grant recipient{'s' if grant_recipients_count != 1 else ''}"
            f"</strong> set up and the grant team has reviewed this"
        )
        self.confirm_grant_recipient_users.label.text = Markup(
            f"It is correct that this grant has <strong {bold}>"
            f"{data_providers_count} grant recipient user{'s' if data_providers_count != 1 else ''}"
            f"</strong> set up and the grant team has reviewed this"
        )
        certification_status = "enabled" if collection.requires_certification else "disabled"
        self.confirm_certification.label.text = Markup(
            f"It is correct that the collection has certification <strong {bold}>{certification_status}</strong>"
        )
        if collection.submission_period_start_date and collection.submission_period_end_date:
            start = format_date_short(collection.submission_period_start_date)
            end = format_date_short(collection.submission_period_end_date)
            self.confirm_submission_dates.label.text = Markup(
                f"The submission dates are <strong {bold}>{start}</strong> until <strong {bold}>{end}</strong>"
            )
        else:
            self.confirm_submission_dates.label.text = "The submission dates have been set"
        multiple_status = "enabled" if collection.allow_multiple_submissions else "disabled"
        self.confirm_multiple_submissions.label.text = Markup(
            f"It is correct that multiple submissions are <strong {bold}>{multiple_status}</strong>"
        )

        if collection.allow_multiple_submissions:
            managed_status = "" if collection.multiple_submissions_are_managed_by_service else "not"
            self.confirm_managed_by_service.label.text = Markup(
                f"It is correct that multiple submissions are "
                f"<strong {bold}>{managed_status} managed</strong> by the service"
            )
            if collection.multiple_submissions_are_managed_by_service:
                managed_count = len(collection.live_submissions)
                self.confirm_managed_submissions_count.label.text = Markup(
                    f"It is correct that this grant has "
                    f"<strong {bold}>{managed_count} managed submission{'s' if managed_count != 1 else ''}</strong> "
                    f"set up"
                )
            else:
                del self.confirm_managed_submissions_count
        else:
            del self.confirm_managed_by_service
            del self.confirm_managed_submissions_count


class PlatformAdminCreateGrantOverrideCertifiersForm(FlaskForm):
    organisation_id = SelectField(
        "Organisation name",
        choices=[],
        widget=GovSelectWithSearch(),
        validators=[DataRequired("Select an organisation")],
    )
    full_name = StringField(
        "Full name",
        validators=[DataRequired("Enter the certifier's full name")],
        widget=GovTextInput(),
    )
    email = EmailField(
        "Email address",
        validators=[DataRequired("Enter an email address"), Email("Enter a valid email address")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Add grant-specific certifier", widget=GovSubmitInput())

    def __init__(self, grant_recipients: Sequence[GrantRecipient]) -> None:
        super().__init__()
        self.organisation_id.choices = [
            ("", ""),
            *[(str(gr.organisation.id), gr.organisation.name) for gr in grant_recipients],
        ]


class PlatformAdminRevokeGrantOverrideCertifiersForm(FlaskForm):
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
    submit = SubmitField("Revoke grant-specific certifier access", widget=GovSubmitInput())

    def __init__(self, grant_recipients: Sequence[GrantRecipient]) -> None:
        super().__init__()
        self.organisation_id.choices = [
            ("", ""),
            *[(str(gr.organisation.id), gr.organisation.name) for gr in grant_recipients],
        ]


class PlatformAdminSetPrivacyPolicyForm(FlaskForm):
    privacy_policy_markdown = TextAreaField(
        "Privacy policy markdown",
        validators=[Optional()],
        widget=GovTextArea(),
    )
    submit = SubmitField("Save privacy policy", widget=GovSubmitInput())


class PlatformAdminForceTracingForm(FlaskForm):
    levels = SelectMultipleField(
        "Request tracing",
        choices=[(e.value, cast(str, uppercase_first(e.value))) for e in TraceLevelEnum],
        widget=GovCheckboxesInput(),
        validators=[Optional()],
        description=(
            "Enable more detailed logs and tracing to be emitted for requests from your browser "
            f"for the next {REQUEST_TRACING_TTL // 60} minutes"
        ),
    )
    submit = SubmitField("Apply", widget=GovSubmitInput())
