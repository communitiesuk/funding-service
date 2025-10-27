import csv
import datetime
from typing import TYPE_CHECKING, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea
from wtforms import SubmitField
from wtforms.fields.choices import SelectField
from wtforms.fields.simple import TextAreaField
from wtforms.validators import DataRequired
from xgovuk_flask_admin import GovSelectWithSearch

from app.common.data.types import OrganisationData, OrganisationType

if TYPE_CHECKING:
    from app.common.data.models import Grant


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


class PlatformAdminMakeGrantLiveForm(FlaskForm):
    submit = SubmitField("Make grant live", widget=GovSubmitInput())


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
