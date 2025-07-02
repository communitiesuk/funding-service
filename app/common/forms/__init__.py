from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput
from wtforms.fields.simple import SubmitField

import app.common.forms.validators as validators

__all__ = ["validators"]


class GenericSubmitForm(FlaskForm):
    submit = SubmitField(widget=GovSubmitInput())
