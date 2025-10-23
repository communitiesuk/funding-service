from typing import TYPE_CHECKING, Sequence

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput
from wtforms import SubmitField
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired
from xgovuk_flask_admin import GovSelectWithSearch

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
